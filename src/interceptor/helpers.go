package main

import (
	"github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
)

func CheckHttpRequestBody(passes func([]byte) bool) func(ctx *WhenContext) bool {
	return func(ctx *WhenContext) bool {
		if ctx.Stage != StageRequestBody {
			return false
		}
		if !ctx.End {
			ctx.Pause()
			return false
		}
		body, err := ctx.GetRequestBody(0, ctx.BodySize)
		if err != nil {
			return false
		}
		if body == nil {
			return false
		}
		return passes(body)
	}
}

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

		return false
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

func DoBlock(ctx *DoContext) bool {
	if ctx.Data == nil {
		proxywasm.ReplaceHttpRequestTrailer("x-blocked", "1")
		ctx.Data = ""
	}

	if ctx.Data.(string) == "" {
		ctx.Data = ctx.GetRequestHeader("x-request-id")
	}
	if ctx.Stage != StageResponseHeaders {
		return false
	}

	// I have a feeling we're calling this method at the wrong time, as response pauses until timeout rather than return immediately
	// On other hand it works in our favour, on other we'll delay stats on the dashboard
	err := proxywasm.SendHttpResponse(418, [][2]string{
		{"x-blocked", "1"},
		{"x-request-id", ctx.Data.(string)},
	}, []byte("hey you"), -1)
	if err != nil {
		ctx.LogInfo("Failed to send HTTP response: " + err.Error())
	}

	// Required to avoid any further processing and passing request to the upstream
	ctx.Pause()
	return true
}
