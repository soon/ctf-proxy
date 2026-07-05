package main

import (
	"os"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

func main() {}

// For some reason TCP requires vm context registration, instead of just tcp context.
type vmContext struct {
	types.DefaultVMContext
}

type pluginContext struct {
	types.DefaultPluginContext
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
}

func (ctx *pluginContext) NewTcpContext(contextID uint32) types.TcpContext {
	return &tcpCtx{skip: undefinedAction}
}

func init() {
	switch {
	case os.Getenv("CTF_PROXY_IS_TCP") != "":
		registerTcpInterceptors()
		proxywasm.SetVMContext(&vmContext{})
		proxywasm.LogInfo("initialized WASM interceptor (tcp)")
	case os.Getenv("CTF_PROXY_IS_HTTP") != "":
		registerHttpInterceptors()
		proxywasm.SetHttpContext(func(contextID uint32) types.HttpContext {
			return &httpCtx{skip: undefinedAction}
		})
		proxywasm.LogInfo("initialized WASM interceptor (http)")
	default:
		panic("interceptor mode not set: specify CTF_PROXY_IS_HTTP or CTF_PROXY_IS_TCP in vm_config environment_variables")
	}
}
