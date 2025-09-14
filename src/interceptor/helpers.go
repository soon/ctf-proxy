package main

import (
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
)

func DoModifyHttpResponseBody(modifyFunc func([]byte) []byte) func(ctx *DoContext) bool {
	return func(ctx *DoContext) bool {
		ctx.DelResponseHeader("content-length")
		ctx.DelResponseHeader("content-encoding")

		if ctx.Stage == StageResponseBody && !ctx.End {
			proxywasm.LogInfo("append-footer-home: buffering response body")
			ctx.Pause()
			return false
		}

		if ctx.Stage == StageResponseBody && ctx.End {
			if b, err := ctx.GetResponseBody(0, ctx.BodySize); err == nil {
				newBody := modifyFunc(b)
				err = ctx.ReplaceResponseBody(newBody)
				if err != nil {
					proxywasm.LogError("append-footer-home: failed to replace response body: " + err.Error())
				}
			}
			proxywasm.LogInfo("append-footer-home: appended footer to response body")
			return true
		}

		return false;
	}
}

func DoReplaceHttpResponseBody(newBody []byte) func(ctx *DoContext) bool {
	return DoModifyHttpResponseBody(func(_ []byte) []byte {
		return newBody
	})
}

func DoPause(ctx *DoContext) bool {
	ctx.Pause()
	return true
}
