// This package defines interface to intercept HTTP traffic.
package main

import (
	"fmt"
	"strings"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

// Stage represents the current HTTP lifecycle stage.
type Stage int

const (
	StageRequestHeaders Stage = iota
	StageRequestBody
	StageResponseHeaders
	StageResponseBody
)

// Human-readable representation of the stage.
func (s Stage) String() string {
	switch s {
	case StageRequestHeaders:
		return "req:headers"
	case StageRequestBody:
		return "req:body"
	case StageResponseHeaders:
		return "resp:headers"
	case StageResponseBody:
		return "resp:body"
	default:
		return "unknown"
	}
}

// An Interceptor is a pair of When/Do functions.
type Interceptor struct {
	// A unique name within a port, for tracing.
	Name string

	// When is called at every stage of the HTTP lifecycle; once it returns true for a stream, it is no longer called for that stream.
	When func(*WhenContext) bool

	// Do will be called once the When matched, at every subsequent stage (including the matching one), until Do returns true.
	Do func(*DoContext) bool
}

// WhenContext provides read-only access for condition evaluation.
type WhenContext struct {
	Stage    Stage
	End      bool // endOfStream (only meaningful on body stages)
	BodySize int  // buffered size visible to the filter

	// Retrieves request header by name. Returns "" if not present or not in request stage.
	GetRequestHeader func(name string) string

	// Retrieves request body bytes in the range [start, start+size). Returns nil if not in request stage.
	GetRequestBody func(start, size int) ([]byte, error)

	// Retrieves response header by name. Returns "" if not present or not in response stage.
	GetResponseHeader func(name string) string

	// Retrieves response body bytes in the range [start, start+size). Returns nil if not in response stage.
	GetResponseBody func(start, size int) ([]byte, error)
}

// DoContext provides full access to modify requests and responses.
type DoContext struct {
	Stage    Stage
	Port     int64
	End      bool // endOfStream (only meaningful on body stages)
	BodySize int  // buffered size visible to the filter

	// Retrieves request header by name. Returns "" if not present or not in request stage.
	GetRequestHeader func(name string) string

	// Sets request header. Does nothing if not in request stage.
	SetRequestHeader func(name, value string)

	// Deletes request header. Does nothing if not in request stage.
	DelRequestHeader func(name string)

	// Retrieves request body bytes in the range [start, start+size). Returns nil if not in request stage.
	GetRequestBody func(start, size int) ([]byte, error)

	// Replaces entire request body. Does nothing if not in request stage.
	ReplaceRequestBody func([]byte) error

	// Retrieves response header by name. Returns "" if not present or not in response stage.
	GetResponseHeader func(name string) string

	// Sets response header. Does nothing if not in response stage.
	SetResponseHeader func(name, value string)

	// Deletes response header. Does nothing if not in response stage.
	DelResponseHeader func(name string)

	// Retrieves response body bytes in the range [start, start+size). Returns nil if not in response stage.
	GetResponseBody func(start, size int) ([]byte, error)

	// Replaces entire response body. Does nothing if not in response stage.
	ReplaceResponseBody func([]byte) error

	// By default ActionContinue; set to ActionPause by Pause().
	resultAction types.Action
}

// Pause makes the current hook return ActionPause (caller should then expect a
// re-entry with more data or with End=true).
func (c *DoContext) Pause() { c.resultAction = types.ActionPause }

// Interceptor registry port -> []Interceptor
var reg = map[int64][]Interceptor{}

// Registers an interceptor for a service port
func RegisterInterceptor(port int64, i Interceptor) {
	reg[port] = append(reg[port], i)
	proxywasm.LogInfo(fmt.Sprintf("registered interceptor name=%s port=%d", i.Name, port))
}

// Context for a single HTTP stream.
type httpCtx struct {
	types.DefaultHttpContext
	// Skip any further stream processing using this action (undefinedAction by default)
	skip types.Action
	// Execute Do for this stream
	do func(*DoContext) bool
}

const undefinedAction types.Action = 0xFFFFFFFF

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
func (h *httpCtx) run(stage Stage, n int, end bool, isReq bool) types.Action {
	if h.skip != undefinedAction {
		return h.skip
	}

runDo:
	if h.do != nil {
		doCtx := h.makeDoCtx(stage, 0, n, end, isReq)
		ignoreFurtherCalls := h.do(doCtx)
		if ignoreFurtherCalls {
			h.do = nil
			h.skip = doCtx.resultAction
		}
		return doCtx.resultAction
	}

	port, err := getIntProperty([]string{"destination", "port"})
	if err != nil {
		proxywasm.LogInfo(fmt.Sprintf("failed to get downstream port: %v", err))
		h.skip = types.ActionContinue
		return types.ActionContinue
	}

	proxywasm.LogInfo(fmt.Sprintf("stage=%s port=%d size=%d end=%t", stage.String(), port, n, end))
	ints := reg[port]
	if len(ints) == 0 {
		proxywasm.LogInfo(fmt.Sprintf("no interceptors registered for port=%d", port))
		h.skip = types.ActionContinue
		return types.ActionContinue
	}

	proxywasm.LogInfo(fmt.Sprintf("processing %d interceptors for port=%d", len(ints), port))

	for _, it := range ints {
		if it.When != nil {
			whenCtx := h.makeWhenCtx(stage, port, n, end, isReq)
			if it.When(whenCtx) {
				proxywasm.LogInfo(fmt.Sprintf("when matched name=%s stage=%s port=%d",
					it.Name, stage.String(), port))
				h.trace(isReq, it.Name)
				h.do = it.Do
				goto runDo
			}
		}
	}

	return types.ActionContinue
}

func (h *httpCtx) makeWhenCtx(stage Stage, port int64, n int, end bool, isReq bool) *WhenContext {
	c := &WhenContext{
		Stage:    stage,
		BodySize: n,
		End:      end,
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
		proxywasm.LogInfo(fmt.Sprintf("get response header key=%s value=%s stage=%s", k, v, stage.String()))
		return v
	}
	c.GetResponseBody = func(start, size int) ([]byte, error) {
		if isReq {
			return nil, nil
		}
		body, err := proxywasm.GetHttpResponseBody(start, size)
		proxywasm.LogInfo(fmt.Sprintf("get response body start=%d size=%d actual_size=%d stage=%s", start, size, len(body), stage.String()))
		return body, err
	}

	return c
}

func (h *httpCtx) makeDoCtx(stage Stage, port int64, n int, end bool, isReq bool) *DoContext {
	c := &DoContext{
		Stage:    stage,
		Port:     port,
		BodySize: n,
		End:      end,
	}

	c.GetRequestHeader = func(k string) string {
		if !isReq {
			return ""
		}
		v, _ := proxywasm.GetHttpRequestHeader(k)
		return v
	}
	c.SetRequestHeader = func(k, v string) {
		if isReq {
			proxywasm.LogInfo(fmt.Sprintf("set request header key=%s value=%s stage=%s", k, v, stage.String()))
			proxywasm.ReplaceHttpRequestHeader(k, v)
		}
	}
	c.DelRequestHeader = func(k string) {
		if isReq {
			proxywasm.RemoveHttpRequestHeader(k)
		}
	}
	c.GetRequestBody = func(start, size int) ([]byte, error) {
		if !isReq {
			return nil, nil
		}
		body, err := proxywasm.GetHttpRequestBody(start, size)
		return body, err
	}
	c.ReplaceRequestBody = func(b []byte) error {
		if !isReq {
			return nil
		}
		return proxywasm.ReplaceHttpRequestBody(b)
	}

	c.GetResponseHeader = func(k string) string {
		if isReq {
			return ""
		}
		v, _ := proxywasm.GetHttpResponseHeader(k)
		return v
	}
	c.SetResponseHeader = func(k, v string) {
		if !isReq {
			proxywasm.ReplaceHttpResponseHeader(k, v)
		}
	}
	c.DelResponseHeader = func(k string) {
		if !isReq {
			proxywasm.RemoveHttpResponseHeader(k)
		}
	}
	c.GetResponseBody = func(start, size int) ([]byte, error) {
		if isReq {
			return nil, nil
		}
		body, err := proxywasm.GetHttpResponseBody(start, size)
		return body, err
	}
	c.ReplaceResponseBody = func(b []byte) error {
		if isReq {
			return nil
		}
		return proxywasm.ReplaceHttpResponseBody(b)
	}

	return c
}

func (h *httpCtx) trace(isReq bool, name string) {
	if isReq {
		curr, _ := proxywasm.GetHttpRequestHeader("x-intercepted-by")
		newValue := appendToken(curr, name)
		proxywasm.ReplaceHttpRequestHeader("x-intercepted-by", newValue)
		proxywasm.LogInfo(fmt.Sprintf("trace request header x-intercepted-by=%s name=%s", newValue, name))
	} else {
		curr, _ := proxywasm.GetHttpResponseHeader("x-intercepted-by")
		newValue := appendToken(curr, name)
		proxywasm.ReplaceHttpResponseHeader("x-intercepted-by", newValue)
		proxywasm.LogInfo(fmt.Sprintf("trace response header x-intercepted-by=%s name=%s", newValue, name))
	}
}

func appendToken(existing, name string) string {
	if existing == "" {
		return name
	}
	for _, p := range strings.Split(existing, ",") {
		if strings.TrimSpace(p) == name {
			return existing
		}
	}
	return existing + "," + name
}

func main() {}

func init() {
	registerInterceptors()

	proxywasm.SetHttpContext(func(contextID uint32) types.HttpContext {
		proxywasm.LogInfo(fmt.Sprintf("creating new HTTP context id=%d", contextID))
		return &httpCtx{skip: undefinedAction}
	})
	proxywasm.LogInfo("initialized WASM HTTP context factory")
}
