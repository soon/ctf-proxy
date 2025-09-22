package main

func registerHttpInterceptors() {
	// RegisterHttpInterceptor(3000, "real interceptor",
	// 	MatchHttpRequest(Matcher{
	// 		Path: MatchPrefix("/manage"),
	// 		Body: func(body []byte) bool {
	// 			m, e := url.ParseQuery(string(body))
	// 			if e != nil {
	// 				return false
	// 			}
	// 			return len(m.Get("pw")) < 10
	// 		},
	// 	}),
	// 	// DoBomb
	// 	DoHttpBlock,
	// )
}

func registerTcpInterceptors() {
	RegisterTcpInterceptor(1337, "acha",
		func(ctx *TcpWhenContext) bool {
			return ctx.Stage == TcpStageDownstreamData && ctx.Size > 300
		},
		DoTcpBlock,
	)
}
