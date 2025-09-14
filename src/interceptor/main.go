package main

import (
	"net/url"
)

func registerInterceptors() {
	RegisterInterceptor(3000, "real interceptor",
		func(ctx *WhenContext) bool {
			if ctx.Data == nil {
				ctx.Data = false
			}
			if ctx.Stage == StageRequestHeaders {
				ctx.Data = ctx.GetRequestHeader(":path") == "/manage"
				return false
			}
			if ctx.Stage == StageRequestBody && ctx.Data.(bool) {
				return CheckHttpRequestBody(func(body []byte) bool {
					m, e := url.ParseQuery(string(body))
					if e != nil {
						return false
					}
					// return m.Get("pw") != m.Get("newpw")
					return len(m.Get("pw")) < 10
				})(ctx)
			}
			return false
		},
		// DoPause,
		DoBlock,
	)

	RegisterInterceptor(3000, "append-footer-home",
		func(ctx *WhenContext) bool {
			return ctx.GetRequestHeader(":path") == "/"
		},
		DoModifyHttpResponseBody(func(body []byte) []byte {
			footer := []byte("\n<!-- Served by wasm-go interceptor -->\n")
			return append(body, footer...)
		}),
	)

	RegisterInterceptor(3000, "block-forbidden",
		func(ctx *WhenContext) bool {
			return ctx.GetRequestHeader(":path") == "/forbidden"
		},
		DoPause,
	)
}
