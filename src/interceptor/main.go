package main

func registerInterceptors() {
	RegisterInterceptor(3000, Interceptor{
		Name: "append-footer-home",
		When: func(ctx *WhenContext) bool {
			return ctx.GetRequestHeader(":path") == "/"
		},
		Do: DoModifyHttpResponseBody(func(body []byte) []byte {
			footer := []byte("\n<!-- Served by wasm-go interceptor -->\n")
			return append(body, footer...)
		}),
	})

	RegisterInterceptor(3000, Interceptor{
		Name: "block-forbidden",
		When: func(ctx *WhenContext) bool {
			return ctx.GetRequestHeader(":path") == "/forbidden"
		},
		Do: DoPause,
	})
}
