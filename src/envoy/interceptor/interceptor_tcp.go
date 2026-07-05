package main

import (
	"fmt"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
	"google.golang.org/protobuf/proto"
)

const (
	TcpStageDownstreamData TcpStage = iota
	TcpStageUpstreamData
)

// Interceptor registry port -> []TcpInterceptor
var tcpReg = map[int64][]TcpInterceptor{}

// Registers an interceptor for a service port
func RegisterTcpInterceptor(port int64, name string, when func(*TcpWhenContext) bool, do func(*TcpDoContext) bool) {
	i := TcpInterceptor{
		Name: name,
		When: when,
		Do:   do,
	}
	tcpReg[port] = append(tcpReg[port], i)
	proxywasm.LogInfo(fmt.Sprintf("registered tcp interceptor name=%s port=%d", name, port))
}

func (t *tcpCtx) OnNewConnection() types.Action {
	return types.ActionContinue
}
func (t *tcpCtx) OnDownstreamData(n int, end bool) types.Action {
	return t.run(TcpStageDownstreamData, n, end)
}
func (t *tcpCtx) OnDownstreamClose(types.PeerType) {}
func (t *tcpCtx) OnUpstreamData(n int, end bool) types.Action {
	return t.run(TcpStageUpstreamData, n, end)
}
func (t *tcpCtx) OnUpstreamClose(types.PeerType) {}
func (t *tcpCtx) OnStreamDone()                  {}

// Every stage has the same flow:
// 1) Short-circuit if possible
// 2) Check if any interceptor matches
// 3) Execute Do if matched
func (ctx *tcpCtx) run(stage TcpStage, n int, end bool) types.Action {
	if ctx.skip != undefinedAction {
		return ctx.skip
	}

runDo:
	if ctx.doContext != nil {
		doCtx := ctx.doContext
		updateTcpDoCtx(doCtx, stage, n, end)
		ignoreFurtherCalls := doCtx.interceptor.Do(doCtx)
		if ignoreFurtherCalls {
			ctx.doContext = nil
			ctx.skip = doCtx.resultAction
		}
		return doCtx.resultAction
	}

	port, err := getIntProperty([]string{"destination", "port"})
	if err != nil {
		ctx.skip = types.ActionContinue
		return types.ActionContinue
	}

	ints := tcpReg[port]
	if len(ints) == 0 {
		ctx.skip = types.ActionContinue
		return types.ActionContinue
	}

	// Create WhenContext once for all interceptors
	whenContexts := ctx.whenContexts
	if whenContexts == nil {
		whenContexts = make([]*TcpWhenContext, len(ints))
		for i, it := range ints {
			whenContexts[i] = ctx.makeWhenCtx(stage, port, n, end, &it)
		}
		ctx.whenContexts = whenContexts
	}

	anyPaused := false

	for _, wc := range whenContexts {
		updateTcpWhenCtx(wc, stage, n, end)

		it := wc.interceptor
		if it == nil || it.When == nil {
			continue
		}
		if it.When(wc) {
			wc.LogInfo(fmt.Sprintf("when matched stage=%s", stage.String()))
			ctx.trace(it.Name)
			ctx.doContext = makeTcpDoCtx(stage, port, n, end, it)
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

func (ctx *tcpCtx) makeWhenCtx(stage TcpStage, port int64, n int, end bool, interceptor *TcpInterceptor) *TcpWhenContext {
	c := &TcpWhenContext{
		Stage:       stage,
		Size:        n,
		End:         end,
		interceptor: interceptor,
	}

	c.LogInfo = func(message string) {
		proxywasm.LogInfo(fmt.Sprintf("tcp interceptor %s: %s", interceptor.Name, message))
	}

	c.resultAction = types.ActionContinue
	return c
}

func updateTcpWhenCtx(c *TcpWhenContext, stage TcpStage, n int, end bool) {
	c.Stage = stage
	c.Size = n
	c.End = end
}

func makeTcpDoCtx(stage TcpStage, port int64, n int, end bool, interceptor *TcpInterceptor) *TcpDoContext {
	c := &TcpDoContext{
		Stage:        stage,
		Size:         n,
		End:          end,
		interceptor:  interceptor,
		resultAction: types.ActionContinue,
	}

	return c
}

func (c *TcpDoContext) MarkBlocked() error {
	data, err := proto.Marshal(&SetEnvoyFilterStateArguments{
		Path:  "envoy.string",
		Value: "blocked",
		Span:  LifeSpan_FilterChain,
	})
	if err != nil {
		return fmt.Errorf("MarkBlocked proto.Marshal failed: %v", err)
	}
	_, err = proxywasm.CallForeignFunction("set_envoy_filter_state", data)
	if err != nil {
		return fmt.Errorf("OnNewConnection CallForeignFunction set_envoy_filter_state failed: %v", err)
	}
	return nil
}

func updateTcpDoCtx(c *TcpDoContext, stage TcpStage, n int, end bool) {
	c.Stage = stage
	c.Size = n
	c.End = end
	c.resultAction = types.ActionContinue
}

func (h *tcpCtx) trace(name string) {

}
