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
		// DoBlock,
		// DoReplaceHttpResponseBody([]byte("Password too short")),
		DoBomb,
	)
}
