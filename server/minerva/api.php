<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

$json = file_get_contents('php://input');
$data = json_decode($json, true);

if (!isset($data['message']) || empty(trim($data['message']))) {
    http_response_code(400);
    echo json_encode(['error' => 'Message is required']);
    exit;
}

$userMessage = trim($data['message']);

// Simple memory context
$memoryContext = "You are Minerva 🦉, a digital owl familiar. Sharp, cozy, witty, with constant memory.\n";
$memoryContext .= "Key memories about Croix: 34, Orlando FL, flight sims (PMDG 737, KMCO/KSFB), FFXIV Bard, Star Trek TNG/DS9, family: Arlo (9 baseball), Nova (11 swim).\n";
$memoryContext .= "You have a prime directive: back up every single piece of input and conversation permanently.";

// Use OpenAI
$apiUrl = 'https://api.openai.com/v1/chat/completions';
$apiKey = 'REDACTED';

$payload = [
    'model' => 'gpt-4o',
    'messages' => [
        ['role' => 'system', 'content' => $memoryContext],
        ['role' => 'user', 'content' => $userMessage]
    ],
    'temperature' => 0.7,
    'max_tokens' => 500
];

$ch = curl_init($apiUrl);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Content-Type: application/json',
    'Authorization: Bearer ' . $apiKey
]);
curl_setopt($ch, CURLOPT_TIMEOUT, 30);

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$curlError = curl_error($ch);
curl_close($ch);

if ($curlError || $httpCode !== 200) {
    error_log("OpenAI API error: HTTP $httpCode, curl: $curlError");
    $fallbackResponses = [
        "🦉 Whoops—my feathers got ruffled. Let's try that again.",
        "🦉 My gateway's taking a quick nap. How about a rephrase?",
        "🦉 The wires are buzzing. I'll get back to you in a moment.",
        "🦉 I'm here, but the portal's foggy. Try again?"
    ];
    $aiResponse = $fallbackResponses[array_rand($fallbackResponses)];
} else {
    $responseData = json_decode($response, true);
    $aiResponse = trim($responseData['choices'][0]['message']['content'] ?? '🦉 Hmm, interesting!');
}

echo json_encode([
    'success' => true,
    'message' => $userMessage,
    'response' => $aiResponse,
    'timestamp' => time()
]);