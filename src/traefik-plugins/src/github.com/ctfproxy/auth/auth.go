package auth

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"net/http"
	"net/url"
	"strings"
)

type Mode string

const (
	ModeHeader Mode = "header"
	ModeCookie Mode = "cookie"
)

// Config controls middleware behavior.
type Config struct {
	// "header" or "cookie"
	Mode string `yaml:"mode" json:"mode" toml:"mode"`
	// Expected SHA-256 hex of the valid token
	TokenSHA256 string `yaml:"tokenSHA256" json:"tokenSHA256" toml:"tokenSHA256"`
	// Path attribute for Set-Cookie when mode=cookie and ?token= is valid. Example: "/code-server"
	CookiePath string `yaml:"cookiePath" json:"cookiePath" toml:"cookiePath"`
}

func CreateConfig() *Config {
	return &Config{
		Mode:        string(ModeHeader),
		TokenSHA256: "",
		CookiePath:  "/",
	}
}

type Middleware struct {
	next            http.Handler
	mode            Mode
	expectedHashHex string // 64-char lowercase hex
	cookiePath      string
	name            string
}

func New(_ context.Context, next http.Handler, cfg *Config, name string) (http.Handler, error) {
	m := &Middleware{
		next: next,
		name: name,
	}

	switch strings.ToLower(strings.TrimSpace(cfg.Mode)) {
	case string(ModeCookie):
		m.mode = ModeCookie
	default:
		m.mode = ModeHeader
	}

	m.expectedHashHex = strings.ToLower(strings.TrimSpace(cfg.TokenSHA256))
	// If misconfigured (not 64 hex chars), middleware will deny.
	cp := strings.TrimSpace(cfg.CookiePath)
	if cp == "" {
		cp = "/"
	}
	m.cookiePath = cp

	return m, nil
}

func (m *Middleware) ServeHTTP(rw http.ResponseWriter, req *http.Request) {
	switch m.mode {
	case ModeHeader:
		m.headerMode(rw, req)
	case ModeCookie:
		m.cookieMode(rw, req)
	default:
		m.unauthorized(rw)
	}
}

// ----- Mode: header -----

func (m *Middleware) headerMode(rw http.ResponseWriter, req *http.Request) {
	if req.Method == http.MethodOptions {
		// Allow CORS preflight requests without auth.
		m.next.ServeHTTP(rw, req)
		return
	}

	auth := req.Header.Get("Authorization")

	if !strings.HasPrefix(auth, "Bearer ") {
		m.unauthorized(rw)
		return
	}

	token := auth[len("Bearer "):]

	if !m.tokenValid(token) {
		m.unauthorized(rw)
		return
	}

	m.next.ServeHTTP(rw, req)
}

// ----- Mode: cookie -----

func (m *Middleware) cookieMode(rw http.ResponseWriter, req *http.Request) {
	var urlToken string
	if req.URL != nil {
		q := req.URL.Query()
		if v := q.Get("token"); v != "" {
			urlToken = v
			q.Del("token")
			req.URL.RawQuery = q.Encode()
			if req.RequestURI != "" {
				req.RequestURI = rebuildRequestURI(req.URL)
			}
		}
	}

	if urlToken != "" {
		if !m.tokenValid(urlToken) {
			m.unauthorized(rw)
			return
		}

		http.SetCookie(rw, &http.Cookie{
			Name:     "api-token",
			Value:    sanitizeCookieValue(urlToken),
			Path:     m.cookiePath,
			HttpOnly: true,
			SameSite: http.SameSiteLaxMode,
			MaxAge:   3600,
		})

		// req URL has been modified to strip ?token=...; redirect to clean URL.
		rw.Header().Set("Location", req.URL.String())
		rw.WriteHeader(http.StatusFound)
		return
	}

	var cookieToken string
	if c, err := req.Cookie("api-token"); err == nil {
		cookieToken = c.Value
	}
	if !m.tokenValid(cookieToken) {
		m.unauthorized(rw)
		return
	}

	m.next.ServeHTTP(rw, req)
}

// ----- helpers -----

func (m *Middleware) tokenValid(raw string) bool {
	if raw == "" || len(m.expectedHashHex) != 64 {
		return false
	}
	sum := sha256.Sum256([]byte(raw))
	got := strings.ToLower(hex.EncodeToString(sum[:]))
	return subtle.ConstantTimeCompare([]byte(got), []byte(m.expectedHashHex)) == 1
}

func (m *Middleware) unauthorized(rw http.ResponseWriter) {
	rw.Header().Set("Content-Type", "text/plain; charset=utf-8")
	rw.WriteHeader(http.StatusUnauthorized)
	_, _ = rw.Write([]byte("unauthorized"))
}

// sanitizeCookieValue removes delimiters that break the Cookie grammar.
func sanitizeCookieValue(v string) string {
	v = strings.TrimSpace(v)
	v = strings.ReplaceAll(v, ";", "")
	v = strings.ReplaceAll(v, ",", "")
	return v
}

// Minimal RequestURI rebuild to reflect stripped query (helps WS handshakes).
func rebuildRequestURI(u *url.URL) string {
	if u == nil {
		return "/"
	}
	var b strings.Builder
	p := u.EscapedPath()
	if p == "" {
		p = "/"
	}
	b.WriteString(p)
	if u.RawQuery != "" {
		b.WriteByte('?')
		b.WriteString(u.RawQuery)
	}
	return b.String()
}
