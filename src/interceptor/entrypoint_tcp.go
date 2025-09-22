//go:build tcp

package main

import (
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

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
	registerTcpInterceptors()
	proxywasm.SetVMContext(&vmContext{})
	proxywasm.LogInfo("initialized WASM TCP context factory")
}
