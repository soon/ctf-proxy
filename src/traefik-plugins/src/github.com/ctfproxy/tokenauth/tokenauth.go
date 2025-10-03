package tokenauth

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
)

type Config struct {
	TokenHash string `json:"tokenHash,omitempty"`
}

func CreateConfig() *Config {
	return &Config{}
}

type TokenAuth struct {
	next      http.Handler
	name      string
	tokenHash string
}

func New(ctx context.Context, next http.Handler, config *Config, name string) (http.Handler, error) {
	if config.TokenHash == "" {
		return nil, fmt.Errorf("tokenHash cannot be empty")
	}

	return &TokenAuth{
		next:      next,
		name:      name,
		tokenHash: config.TokenHash,
	}, nil
}

func (t *TokenAuth) ServeHTTP(rw http.ResponseWriter, req *http.Request) {
	token := req.URL.Query().Get("tkn")
	fromQuery := token != ""

	if token == "" {
		cookie, err := req.Cookie("code_server_token")
		if err == nil {
			token = cookie.Value
		}
	}
	if token == "" {
		token = req.Header.Get("Authorization")
		if len(token) > 7 && token[:7] == "Bearer " {
			token = token[7:]
		}
	}

	if token == "" {
		http.Error(rw, "Unauthorized: token required", http.StatusUnauthorized)
		return
	}

	hash := sha256.Sum256([]byte(token))
	tokenHash := hex.EncodeToString(hash[:])

	if tokenHash != t.tokenHash {
		http.Error(rw, "Unauthorized: invalid token", http.StatusUnauthorized)
		return
	}

	if fromQuery {
		http.SetCookie(rw, &http.Cookie{
			Name:     "code_server_token",
			Value:    token,
			Path:     "/code-server",
			MaxAge:   604800,
			HttpOnly: false,
			SameSite: http.SameSiteNoneMode,
			Secure:   false,
		})
	}

	req.Header.Set("X-Forwarded-Token", token)
	t.next.ServeHTTP(rw, req)
}