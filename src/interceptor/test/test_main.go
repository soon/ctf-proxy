package main

import ()

func registerHttpInterceptors() {
	RegisterHttpInterceptor(3000, "path match prefix",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/intercept"),
		}), DoHttpBlock)
}
