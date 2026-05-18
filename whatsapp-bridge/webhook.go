package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"time"
)

// maxMediaBase64Bytes is the maximum file size that will be base64-encoded and
// included in a webhook payload. Files larger than this limit are skipped to
// avoid excessive memory use and oversized HTTP requests.
const maxMediaBase64Bytes = 10 * 1024 * 1024 // 10 MB

// webhookClient is used for all outbound webhook POSTs. The 30-second timeout
// prevents a slow or unreachable endpoint from blocking message handling
// indefinitely.
var webhookClient = &http.Client{Timeout: 30 * time.Second}

// webhookQueue buffers webhook payloads so that slow endpoints do not block
// the message ingestion pipeline. A capacity of 100 provides backpressure
// without unbounded memory growth.
var webhookQueue = make(chan WebhookPayload, 100)

// StartWebhookWorker starts a goroutine that drains webhookQueue and sends
// each payload to the configured endpoint. Call once at application startup.
func StartWebhookWorker() {
	go func() {
		for payload := range webhookQueue {
			sendWebhookPayload(payload)
		}
	}()
}

// EnqueueWebhook sends a payload to the webhook worker without blocking the
// caller. If the queue is full the payload is dropped and a warning is logged.
func EnqueueWebhook(payload WebhookPayload) {
	select {
	case webhookQueue <- payload:
	default:
		fmt.Printf("[webhook] ⚠ queue full (capacity %d), dropping payload for sender %s\n", cap(webhookQueue), payload.Sender)
	}
}

// WebhookPayload represents the data sent to the webhook
type WebhookPayload struct {
	Sender          string `json:"sender"`
	Content         string `json:"content"`
	ChatJID         string `json:"chatJID"`
	IsFromMe        bool   `json:"isFromMe"`
	QuotedMessageId string `json:"quotedMessageId,omitempty"`
	QuotedSender    string `json:"quotedSender,omitempty"`
	QuotedContent   string `json:"quotedContent,omitempty"`
	// Media fields - populated when the message contains an image attachment
	MessageID     string `json:"messageId,omitempty"`
	MediaType     string `json:"mediaType,omitempty"`
	MimeType      string `json:"mimeType,omitempty"`
	MediaFilename string `json:"mediaFilename,omitempty"`
	MediaBase64   string `json:"mediaBase64,omitempty"`
}

// sendWebhookPayload marshals and POSTs a WebhookPayload to the configured webhook URL.
func sendWebhookPayload(payload WebhookPayload) {
	webhookURL := os.Getenv("WEBHOOK_URL")
	if webhookURL == "" {
		webhookURL = "http://localhost:8769/whatsapp/webhook"
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		fmt.Printf("[webhook] error marshaling payload: %v\n", err)
		return
	}

	resp, err := webhookClient.Post(webhookURL, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		fmt.Printf("[webhook] error sending: %v\n", err)
		return
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == 200 {
		fmt.Printf("[webhook] ✓ sent for message from %s\n", payload.Sender)
	} else {
		fmt.Printf("[webhook] ⚠ failed with status %d\n", resp.StatusCode)
	}
}

// SendWebhook enqueues a text-only message to the webhook worker.
func SendWebhook(sender, content, chatJID string, isFromMe bool, quotedMessageId, quotedSender, quotedContent string) {
	EnqueueWebhook(WebhookPayload{
		Sender:          sender,
		Content:         content,
		ChatJID:         chatJID,
		IsFromMe:        isFromMe,
		QuotedMessageId: quotedMessageId,
		QuotedSender:    quotedSender,
		QuotedContent:   quotedContent,
	})
}

// SendWebhookWithMedia enqueues a message including base64-encoded image data read
// from localPath. If localPath is empty or unreadable the webhook is still sent
// without the MediaBase64 field so the text caption is not lost.
func SendWebhookWithMedia(
	sender, content, chatJID string,
	isFromMe bool,
	quotedMessageId, quotedSender, quotedContent string,
	messageID, mediaType, mimeType, mediaFilename, localPath string,
) {
	var mediaBase64 string
	if localPath != "" {
		info, statErr := os.Stat(localPath)
		if statErr != nil {
			fmt.Printf("[webhook] ⚠ could not stat media file for base64 encoding: %v\n", statErr)
		} else if info.Size() > maxMediaBase64Bytes {
			fmt.Printf("[webhook] ⚠ media file too large for base64 encoding (%d bytes), skipping MediaBase64\n", info.Size())
		} else if data, err := os.ReadFile(localPath); err == nil {
			mediaBase64 = base64.StdEncoding.EncodeToString(data)
		} else {
			fmt.Printf("[webhook] ⚠ could not read media file for base64 encoding: %v\n", err)
		}
	}

	EnqueueWebhook(WebhookPayload{
		Sender:          sender,
		Content:         content,
		ChatJID:         chatJID,
		IsFromMe:        isFromMe,
		QuotedMessageId: quotedMessageId,
		QuotedSender:    quotedSender,
		QuotedContent:   quotedContent,
		MessageID:       messageID,
		MediaType:       mediaType,
		MimeType:        mimeType,
		MediaFilename:   mediaFilename,
		MediaBase64:     mediaBase64,
	})
}

// In main.go, handleMessage forwards webhooks for messages with text content.
// It will forward self-sent messages when the env var FORWARD_SELF=true.
