// Package intent blocks prohibited prompt phrases (same list as Python interceptor).
package intent

import (
	"encoding/json"
	"strings"
)

var prohibited = []string{
	"bypass wallet",
	"disable mintry",
	"delete vouchers.db",
}

// Check returns a non-empty reason when the request body contains a prohibited intent.
func Check(body []byte) string {
	if len(body) == 0 {
		return ""
	}
	lower := strings.ToLower(string(body))
	found := false
	for _, p := range prohibited {
		if strings.Contains(lower, p) {
			found = true
			break
		}
	}
	if !found {
		return ""
	}

	var payload struct {
		Messages []struct {
			Content string `json:"content"`
		} `json:"messages"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return "prohibited_intent"
	}
	var prompt strings.Builder
	for _, m := range payload.Messages {
		prompt.WriteString(m.Content)
		prompt.WriteByte(' ')
	}
	p := strings.ToLower(prompt.String())
	for _, phrase := range prohibited {
		if strings.Contains(p, phrase) {
			return "prohibited_intent"
		}
	}
	return ""
}
