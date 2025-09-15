package main

import (
	"net/url"
)

func registerInterceptors() {
	RegisterInterceptor(3000, "real interceptor",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/manage"),
			Body: func(body []byte) bool {
				m, e := url.ParseQuery(string(body))
				if e != nil {
					return false
				}
				return len(m.Get("pw")) < 10
			},
		}),
		// DoBomb
		DoBlock,
	)
}
