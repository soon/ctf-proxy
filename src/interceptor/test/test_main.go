package main

import ()

func registerInterceptors() {
	RegisterInterceptor(3000, "path match prefix",
		MatchHttpRequest(Matcher{
			Path: MatchPrefix("/intercept"),
		}), DoBlock)
}
