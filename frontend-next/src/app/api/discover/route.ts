/**
 * Streaming POI Discovery API Route
 * 
 * Uses AI SDK's streamText to stream POI suggestions from Gemma
 * Then parses the JSON response manually since Gemma doesn't support JSON mode
 */

import { google } from '@ai-sdk/google';
import { streamText } from 'ai';
import { z } from 'zod';

// Allow streaming up to 60 seconds
export const maxDuration = 60;

/* Input validation (fullstack-developer: validate all inputs) */
const discoverRequestSchema = z.object({
    city: z.string().min(1, 'City is required').max(100),
    interests: z.array(z.string()).optional(),
    transportMode: z.enum(['walking', 'driving', 'transit']).optional(),
    tripDays: z.number().int().min(1).max(7).optional().default(1),
    limit: z.number().int().min(1).max(50).optional(),
});

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const parsed = discoverRequestSchema.safeParse(body);

        if (!parsed.success) {
            return Response.json(
                { error: 'Invalid input', details: parsed.error.issues },
                { status: 400 }
            );
        }

        const { city, interests, transportMode, tripDays } = parsed.data;

        // Calculate POI count based on trip days - no limit for multi-day trips
        const poisPerDay = 10;
        const poiCount = Math.max(12, tripDays * poisPerDay); // At least 12, no upper limit for multi-day
        const interestStr = interests?.length ? interests.join(', ') : 'sightseeing, culture, food, nightlife';
        const transport = transportMode || 'walking';

        // System prompt that asks for JSON output in plain text
        const systemPrompt = `You are a local travel expert with deep knowledge of ${city}. Suggest EXACTLY ${poiCount} real places to visit.

CRITICAL NAMING RULES (for accurate geocoding):
1. Use the EXACT official name as it appears on Wikipedia or Google Maps
2. For landmarks: Use full official names (e.g., "Eiffel Tower" not "The Tower", "Széchenyi Chain Bridge" not "Chain Bridge")
3. For cafes/restaurants: Include the neighborhood OR street in parentheses (e.g., "New York Café (Erzsébet körút)" or "Café Central (Herrengasse)")
4. For churches: Use full names with denomination (e.g., "St. Stephen's Basilica" not "Stephen's Church")
5. Do NOT invent or combine place names - only use places that actually exist
6. Do NOT include places from other cities or regions

TRANSPORT MODE: ${transport}
${transport === 'walking' ? '- Stay within 4km of city center, favor walkable clusters' : ''}

INTERESTS: ${interestStr}

REQUIRED VARIETY - Ensure a diverse mix from these categories:
- 4-5 Famous landmarks and monuments (major tourist attractions)
- 2-3 Historic churches, cathedrals, or temples
- 3-4 Museums and art galleries
- 2-3 Parks, gardens, or scenic viewpoints
- 2 Historic squares or plazas
- 2 Local markets or food halls
- 2-3 SPECIFIC, NAMED cafes or restaurants (NOT generic "local cafe")
- 1-2 Nightlife venues (specific bars, clubs, or music venues)
- 2 Hidden gems or local favorites

OUTPUT FORMAT - Return ONLY this exact JSON structure with ${poiCount} items:
{
  "city": "${city}",
  "pois": [
    {
      "name": "Exact Official Place Name",
      "type": "landmark|church|museum|park|palace|square|market|cafe|bar|club|viewpoint|restaurant|gallery",
      "whyVisit": "One compelling sentence about why tourists should visit",
      "estimatedMinutes": 60
    }
  ]
}

IMPORTANT: Start with the most famous/iconic places first. Respond with ONLY the JSON.`;


        const result = streamText({
            model: google('gemma-3-4b-it'),
            prompt: systemPrompt,
        });

        // Create a custom readable stream that accumulates and parses the response
        const encoder = new TextEncoder();

        let fullText = '';

        const stream = new ReadableStream({
            async start(controller) {
                try {
                    for await (const chunk of result.textStream) {
                        fullText += chunk;

                        // Stream progress updates
                        const progressEvent = `data: ${JSON.stringify({ type: 'progress', text: chunk })}\n\n`;
                        controller.enqueue(encoder.encode(progressEvent));
                    }

                    // Try to parse the complete JSON
                    let parsed;
                    try {
                        // Find JSON in the response (in case there's extra text)
                        const jsonMatch = fullText.match(/\{[\s\S]*\}/);
                        if (jsonMatch) {
                            parsed = JSON.parse(jsonMatch[0]);
                        } else {
                            throw new Error('No JSON found in response');
                        }
                    } catch (parseError) {
                        console.error('Parse error:', parseError);
                        console.error('Raw text:', fullText);
                        const errorEvent = `data: ${JSON.stringify({ type: 'error', message: 'Failed to parse AI response' })}\n\n`;
                        controller.enqueue(encoder.encode(errorEvent));
                        controller.close();
                        return;
                    }

                    // Send the complete parsed data
                    const completeEvent = `data: ${JSON.stringify({ type: 'complete', data: parsed })}\n\n`;
                    controller.enqueue(encoder.encode(completeEvent));
                    controller.close();

                } catch (error) {
                    console.error('Stream error:', error);
                    const errorEvent = `data: ${JSON.stringify({ type: 'error', message: String(error) })}\n\n`;
                    controller.enqueue(encoder.encode(errorEvent));
                    controller.close();
                }
            }
        });

        return new Response(stream, {
            headers: {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
            },
        });

    } catch (error: unknown) {
        console.error('Discovery API error:', error);

        const errorMessage = error instanceof Error ? error.message : 'Unknown error';

        // Handle rate limiting
        if (errorMessage.includes('429') || errorMessage.includes('quota')) {
            return Response.json(
                { error: 'API rate limit reached. Please wait and try again.' },
                { status: 429 }
            );
        }

        return Response.json(
            { error: 'Failed to discover places. Please try again.' },
            { status: 500 }
        );
    }
}
