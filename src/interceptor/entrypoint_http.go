//go:build http

package main

import (
	"fmt"

	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

func init() {
	registerHttpInterceptors()
	proxywasm.SetHttpContext(func(contextID uint32) types.HttpContext {
		proxywasm.LogInfo(fmt.Sprintf("creating new HTTP context id=%d", contextID))
		return &httpCtx{skip: undefinedAction}
	})
	proxywasm.LogInfo("initialized WASM HTTP context factory")
}
