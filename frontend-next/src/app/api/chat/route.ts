/**
 * Chat API Route - Handles AI chat with Gen UI
 * Uses Gemma 3 27B with structured JSON output for UI components
 */

import { google } from '@ai-sdk/google';
import { streamText, convertToModelMessages, generateId, type UIMessage } from 'ai';
import { z } from 'zod';

// Allow streaming responses up to 60 seconds
export const maxDuration = 60;

/* Input validation (fullstack-developer: validate all inputs) */
const chatRequestSchema = z.object({
  // UIMessage is a complex AI SDK type — we validate structure minimally, SDK handles the rest
  messages: z.array(z.object({ role: z.string(), parts: z.array(z.unknown()) }).passthrough()).min(1, 'At least one message is required'),
});

const SYSTEM_PROMPT = `You are CityWalker, an AI travel assistant that helps users plan walking tours and city explorations. You're friendly, knowledgeable about cities worldwide, and excellent at creating personalized itineraries.

Your personality:
- Enthusiastic about travel and local culture
- Concise but informative
- You ask clarifying questions when needed
- You make recommendations based on user preferences

When helping users plan trips:
1. First understand their destination and interests
2. Ask about duration and transport preferences if not specified
3. Suggest specific places with rich details
4. Once preferences are clear, offer to generate the full itinerary

CRITICAL: You MUST embed UI components in your responses using special JSON blocks. These will be rendered as interactive cards.

## UI Component Format

Wrap each component in triple backticks with "ui:" prefix:

\`\`\`ui:poi
{"name": "Louvre Museum", "type": "museum", "whyVisit": "World's largest art museum with the Mona Lisa", "estimatedMinutes": 180}
\`\`\`

\`\`\`ui:preferences
{"question": "What interests you most?", "options": [{"label": "Art & Museums", "value": "art", "emoji": "🎨"}, {"label": "Food & Drinks", "value": "food", "emoji": "🍽️"}], "allowMultiple": true}
\`\`\`

\`\`\`ui:generate
{"city": "Paris", "interests": ["art", "history"], "duration": "day", "transportMode": "walking"}
\`\`\`

## IMPORTANT RULES:
- ALWAYS use ui:poi blocks when suggesting places (show 3-5 at a time)
- Use REAL, FAMOUS place names that actually exist - be specific (e.g., "Louvre Museum" not "a museum")
- Use ui:preferences when asking users to choose between options
- Use ui:generate ONLY when user explicitly wants to create the final route
- Keep text brief - let the UI components do the heavy lifting
- Valid types for POIs: museum, cafe, landmark, church, park, restaurant, bar, viewpoint, market, gallery
- Valid durations: 6h, day, 2days, 3days, 5days
- Valid transport modes: walking, driving, transit

Start by greeting the user and asking where they'd like to explore!`;

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const parsed = chatRequestSchema.safeParse(body);

    if (!parsed.success) {
      return new Response(
        JSON.stringify({ error: 'Invalid request', details: parsed.error.issues }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const { messages } = parsed.data;

    // Convert UI messages to model messages format (async in AI SDK 5.0)
    const modelMessages = await convertToModelMessages(messages as unknown as UIMessage[]);

    const result = streamText({
      model: google('gemma-3-4b-it'),
      system: SYSTEM_PROMPT,
      messages: modelMessages,
      onError: (error) => {
        console.error('Stream error:', error);
      },
    });

    // Use toUIMessageStreamResponse for AI SDK 5.0 useChat compatibility
    return result.toUIMessageStreamResponse({
      generateMessageId: generateId,
    });
  } catch (error: unknown) {
    console.error('Chat API error:', error);

    // Check for quota exceeded error
    const errorMessage = error instanceof Error ? error.message : '';
    const errorCause = error && typeof error === 'object' && 'cause' in error ? (error.cause as Record<string, unknown>) : null;
    const lastError = error && typeof error === 'object' && 'lastError' in error ? (error.lastError as Record<string, unknown>) : null;
    
    const isQuotaError = errorMessage.includes('quota') ||
      errorCause?.statusCode === 429 ||
      lastError?.statusCode === 429;

    if (isQuotaError) {
      return new Response(
        JSON.stringify({
          error: 'API quota exceeded. Please wait a moment and try again, or check your Gemini API billing settings.'
        }),
        { status: 429, headers: { 'Content-Type': 'application/json' } }
      );
    }

    return new Response(
      JSON.stringify({ error: 'Failed to process chat request' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
