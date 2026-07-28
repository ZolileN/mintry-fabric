// Package pricing mirrors src/mintry/core/pricing.py for sidecar metering.
package pricing

import "strings"

var table = map[string]struct{ In, Out float64 }{
	"gpt-4o":           {0.0000025, 0.00001},
	"gpt-4o-mini":      {0.00000015, 0.0000006},
	"gpt-4.1":          {0.000002, 0.000008},
	"claude-sonnet-4":  {0.000003, 0.000015},
	"gemini-2.0-flash": {0.0000001, 0.0000004},
	"gemini-2.5-flash": {0.00000015, 0.0000006},
	"gemini-2.5-pro":   {0.00000125, 0.00001},
}

var defaultRate = struct{ In, Out float64 }{0.000005, 0.000005}

func CalculateCost(model string, promptTokens, completionTokens int) float64 {
	rate := defaultRate
	lower := strings.ToLower(model)
	if r, ok := table[lower]; ok {
		rate = r
	} else {
		for name, r := range table {
			if strings.HasPrefix(lower, name) {
				rate = r
				break
			}
		}
	}
	return float64(promptTokens)*rate.In + float64(completionTokens)*rate.Out
}
