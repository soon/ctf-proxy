// This package defines interface to intercept HTTP traffic.
package main

import (
	"fmt"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

const (
	StageRequestHeaders HttpStage = iota
	StageRequestBody
	StageResponseHeaders
	StageResponseBody
)

// Pause makes the current hook return ActionPause (caller should then expect a
// re-entry with more data or with End=true).
func (c *HttpWhenContext) Pause() { c.resultAction = types.ActionPause }

// Pause makes the current hook return ActionPause (caller should then expect a
// re-entry with more data or with End=true).
func (c *HttpDoContext) Pause() { c.resultAction = types.ActionPause }

// Interceptor registry port -> []HttpInterceptor
var httpReg = map[int64][]HttpInterceptor{}

// Registers an interceptor for a service port
func RegisterHttpInterceptor(port int64, name string, when func(*HttpWhenContext) bool, do func(*HttpDoContext) bool) {
	i := HttpInterceptor{
		Name: name,
		When: when,
		Do:   do,
	}
	httpReg[port] = append(httpReg[port], i)
	proxywasm.LogInfo(fmt.Sprintf("registered http interceptor name=%s port=%d", name, port))
}

func (h *httpCtx) OnHttpRequestHeaders(n int, end bool) types.Action {
	return h.run(StageRequestHeaders, n, end, true)
}
func (h *httpCtx) OnHttpRequestBody(n int, end bool) types.Action {
	return h.run(StageRequestBody, n, end, true)
}
func (h *httpCtx) OnHttpResponseHeaders(n int, end bool) types.Action {
	return h.run(StageResponseHeaders, n, end, false)
}
func (h *httpCtx) OnHttpResponseBody(n int, end bool) types.Action {
	return h.run(StageResponseBody, n, end, false)
}

// Every stage has the same flow:
// 1) Short-circuit if possible
// 2) Check if any interceptor matches
// 3) Execute Do if matched
func (h *httpCtx) run(stage HttpStage, n int, end bool, isReq bool) types.Action {
	if h.skip != undefinedAction {
		return h.skip
	}

runDo:
	if h.doContext != nil {
		doCtx := h.doContext
		updateHttpDoCtx(doCtx, stage, n, end)
		ignoreFurtherCalls := doCtx.interceptor.Do(doCtx)
		if ignoreFurtherCalls {
			h.doContext = nil
			h.skip = doCtx.resultAction
		}
		return doCtx.resultAction
	}

	port, err := getIntProperty([]string{"destination", "port"})
	if err != nil {
		h.skip = types.ActionContinue
		return types.ActionContinue
	}

	ints := httpReg[port]
	if len(ints) == 0 {
		h.skip = types.ActionContinue
		return types.ActionContinue
	}

	// Create WhenContext once for all interceptors
	whenContexts := h.whenContexts
	if whenContexts == nil {
		whenContexts = make([]*HttpWhenContext, len(ints))
		for i, it := range ints {
			whenContexts[i] = h.makeWhenCtx(stage, port, n, end, isReq, &it)
		}
		h.whenContexts = whenContexts
	}

	anyPaused := false

	for _, wc := range whenContexts {
		updateHttpWhenCtx(wc, stage, n, end)

		it := wc.interceptor
		if it == nil || it.When == nil {
			continue
		}
		if it.When(wc) {
			wc.LogInfo(fmt.Sprintf("when matched stage=%s", stage.String()))
			h.trace(isReq, it.Name)
			h.doContext = makeHttpDoCtx(stage, port, n, end, it)
			goto runDo
		}
		if wc.resultAction == types.ActionPause {
			anyPaused = true
		}
	}

	if anyPaused {
		return types.ActionPause
	}
	return types.ActionContinue
}

func (h *httpCtx) makeWhenCtx(stage HttpStage, port int64, n int, end bool, isReq bool, interceptor *HttpInterceptor) *HttpWhenContext {
	c := &HttpWhenContext{
		Stage:        stage,
		BodySize:     n,
		End:          end,
		interceptor:  interceptor,
		resultAction: types.ActionContinue,
	}

	c.GetRequestHeader = func(k string) string {
		if !isReq {
			return ""
		}
		v, _ := proxywasm.GetHttpRequestHeader(k)
		return v
	}
	c.GetRequestBody = func(start, size int) ([]byte, error) {
		if !isReq {
			return nil, nil
		}
		body, err := proxywasm.GetHttpRequestBody(start, size)
		return body, err
	}
	c.GetResponseHeader = func(k string) string {
		if isReq {
			return ""
		}
		v, _ := proxywasm.GetHttpResponseHeader(k)
		return v
	}
	c.GetResponseBody = func(start, size int) ([]byte, error) {
		if isReq {
			return nil, nil
		}
		body, err := proxywasm.GetHttpResponseBody(start, size)
		return body, err
	}
	c.LogInfo = func(message string) {
		if c.interceptor != nil && c.interceptor.Name != "" {
			proxywasm.LogInfo(fmt.Sprintf("[%s (when)] %s", c.interceptor.Name, message))
		} else {
			proxywasm.LogInfo(message)
		}
	}

	return c
}

func updateHttpWhenCtx(c *HttpWhenContext, stage HttpStage, n int, end bool) {
	c.Stage = stage
	c.BodySize = n
	c.End = end
	c.resultAction = types.ActionContinue
}

func makeHttpDoCtx(stage HttpStage, port int64, n int, end bool, interceptor *HttpInterceptor) *HttpDoContext {
	c := &HttpDoContext{
		Stage:        stage,
		Port:         port,
		BodySize:     n,
		End:          end,
		interceptor:  interceptor,
		resultAction: types.ActionContinue,
	}

	c.GetRequestHeader = func(k string) string {
		if c.Stage != StageRequestHeaders {
			c.LogWarn("GetRequestHeader called at wrong stage: " + c.Stage.String())
			return ""
		}
		v, _ := proxywasm.GetHttpRequestHeader(k)
		return v
	}
	c.SetRequestHeader = func(k, v string) {
		if c.Stage != StageRequestHeaders {
			c.LogWarn("SetRequestHeader called at wrong stage: " + c.Stage.String())
			return
		}
		proxywasm.ReplaceHttpRequestHeader(k, v)
	}
	c.DelRequestHeader = func(k string) {
		if c.Stage != StageRequestHeaders {
			c.LogWarn("DelRequestHeader called at wrong stage: " + c.Stage.String())
			return
		}
		proxywasm.RemoveHttpRequestHeader(k)
	}
	c.GetRequestBody = func(start, size int) ([]byte, error) {
		if c.Stage != StageRequestBody {
			c.LogWarn("GetRequestBody called at wrong stage: " + c.Stage.String())
			return nil, nil
		}
		body, err := proxywasm.GetHttpRequestBody(start, size)
		return body, err
	}
	c.ReplaceRequestBody = func(b []byte) error {
		if c.Stage != StageRequestBody {
			c.LogWarn("ReplaceRequestBody called at wrong stage: " + c.Stage.String())
			return nil
		}
		return proxywasm.ReplaceHttpRequestBody(b)
	}

	c.GetResponseHeader = func(k string) string {
		if c.Stage != StageResponseHeaders {
			c.LogWarn("GetResponseHeader called at wrong stage: " + c.Stage.String())
			return ""
		}
		v, _ := proxywasm.GetHttpResponseHeader(k)
		return v
	}
	c.SetResponseHeader = func(k, v string) {
		if c.Stage != StageResponseHeaders {
			c.LogWarn("SetResponseHeader called at wrong stage: " + c.Stage.String())
			return
		}
		proxywasm.ReplaceHttpResponseHeader(k, v)
	}
	c.DelResponseHeader = func(k string) {
		if c.Stage != StageResponseHeaders {
			c.LogWarn("DelResponseHeader called at wrong stage: " + c.Stage.String())
			return
		}
		proxywasm.RemoveHttpResponseHeader(k)
	}
	c.GetResponseBody = func(start, size int) ([]byte, error) {
		if c.Stage != StageResponseBody {
			c.LogWarn("GetResponseBody called at wrong stage: " + c.Stage.String())
			return nil, nil
		}
		body, err := proxywasm.GetHttpResponseBody(start, size)
		return body, err
	}
	c.ReplaceResponseBody = func(b []byte) error {
		if c.Stage != StageResponseBody {
			c.LogWarn("ReplaceResponseBody called at wrong stage: " + c.Stage.String())
			return nil
		}
		return proxywasm.ReplaceHttpResponseBody(b)
	}

	c.LogInfo = func(message string) {
		if c.interceptor != nil && c.interceptor.Name != "" {
			proxywasm.LogInfo(fmt.Sprintf("[%s (do)] %s", c.interceptor.Name, message))
		} else {
			proxywasm.LogInfo(message)
		}
	}
	c.LogWarn = func(message string) {
		if c.interceptor != nil && c.interceptor.Name != "" {
			proxywasm.LogWarn(fmt.Sprintf("[%s (do)] %s", c.interceptor.Name, message))
		} else {
			proxywasm.LogWarn(message)
		}
	}

	return c
}

func updateHttpDoCtx(c *HttpDoContext, stage HttpStage, n int, end bool) {
	c.Stage = stage
	c.BodySize = n
	c.End = end
	c.resultAction = types.ActionContinue
}

func (h *httpCtx) trace(isReq bool, name string) {
	if isReq {
		proxywasm.ReplaceHttpRequestHeader("x-intercepted-by", name)
	} else {
		proxywasm.ReplaceHttpResponseHeader("x-intercepted-by", name)
	}
}
