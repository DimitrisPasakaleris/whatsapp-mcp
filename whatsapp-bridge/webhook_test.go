package main

import (
	"io"
	"net/http"
	"strings"
	"testing"
)

type webhookRoundTripper func(*http.Request) (*http.Response, error)

func (roundTrip webhookRoundTripper) RoundTrip(request *http.Request) (*http.Response, error) {
	return roundTrip(request)
}

func TestEmptyWebhookURLDisablesForwarding(t *testing.T) {
	oldClient := webhookClient
	t.Cleanup(func() { webhookClient = oldClient })
	calls := 0
	webhookClient = &http.Client{Transport: webhookRoundTripper(func(request *http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader("")), Header: make(http.Header)}, nil
	})}
	for _, value := range []string{"", "   "} {
		t.Setenv("WEBHOOK_URL", value)
		sendWebhookPayload(WebhookPayload{Content: "fixture"})
	}
	if calls != 0 {
		t.Fatalf("disabled webhook made %d network requests", calls)
	}
}

func TestConfiguredWebhookReceivesPayload(t *testing.T) {
	t.Setenv("WEBHOOK_URL", "https://example.invalid/webhook")
	oldClient := webhookClient
	t.Cleanup(func() { webhookClient = oldClient })
	calls := 0
	webhookClient = &http.Client{Transport: webhookRoundTripper(func(request *http.Request) (*http.Response, error) {
		calls++
		if request.URL.String() != "https://example.invalid/webhook" || request.Method != http.MethodPost {
			t.Fatalf("unexpected webhook request: %s %s", request.Method, request.URL)
		}
		return &http.Response{StatusCode: http.StatusNoContent, Body: io.NopCloser(strings.NewReader("")), Header: make(http.Header)}, nil
	})}
	sendWebhookPayload(WebhookPayload{Content: "fixture"})
	if calls != 1 {
		t.Fatalf("configured webhook made %d requests, want 1", calls)
	}
}
