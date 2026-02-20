/**
 * Multi-Photo Image API Route
 * 
 * Returns 3-5 images per POI for carousel display.
 * Fetches from multiple free sources in parallel:
 * 1. Wikipedia - Main landmark image
 * 2. Wikimedia Commons - Additional angles (3-4 images)
 * 3. Unsplash - Atmosphere/backup shots
 * 
 * Smart latency: Returns first image fast, fetches rest in parallel
 */

const WIKIPEDIA_API = 'https://en.wikipedia.org/api/rest_v1/page/summary';
const WIKIMEDIA_SEARCH = 'https://commons.wikimedia.org/w/api.php';
const UNSPLASH_API = 'https://api.unsplash.com/search/photos';

const UNSPLASH_ACCESS_KEY = process.env.UNSPLASH_ACCESS_KEY;

import { z } from 'zod';

/* Input validation (fullstack-developer: validate all inputs) */
const imageRequestSchema = z.object({
    places: z.array(z.object({
        name: z.string().min(1),
        city: z.string().min(1),
        type: z.string().optional(),
    })).min(1, 'At least one place is required').max(20),
});

export interface PlaceImages {
    name: string;
    images: string[];  // Array of image URLs (3-5 images)
    sources: string[]; // Source for each image
}

// Wikipedia REST API - Get main image
async function getWikipediaImage(placeName: string, city: string): Promise<string | null> {
    const queries = [placeName, `${placeName} ${city}`, `${placeName} (${city})`];

    for (const query of queries) {
        try {
            const response = await fetch(
                `${WIKIPEDIA_API}/${encodeURIComponent(query)}`,
                {
                    headers: {
                        'User-Agent': 'CityWalker/1.0 (travel-app)',
                        'Accept': 'application/json'
                    },
                }
            );

            if (response.ok) {
                const data = await response.json();
                if (data.thumbnail?.source) {
                    return data.thumbnail.source.replace(/\/\d+px-/, '/800px-');
                }
                if (data.originalimage?.source) {
                    return data.originalimage.source;
                }
            }
        } catch {
            // Try next query
        }
    }
    return null;
}

// Filter out generic/stock images by checking filename patterns
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function isRelevantImage(url: string, _placeName: string): boolean {
    const urlLower = url.toLowerCase();

    // Blacklist generic stock image patterns
    const genericPatterns = [
        'stock', 'generic', 'placeholder', 'example', 'sample',
        'icon', 'logo', 'blank', 'default', 'untitled', 'image_'
    ];
    if (genericPatterns.some(p => urlLower.includes(p))) return false;

    // Blacklist map/diagram/chart images
    const mapPatterns = ['map', 'diagram', 'chart', 'graph', 'plan', 'layout'];
    if (mapPatterns.some(p => urlLower.includes(p))) return false;

    return true; // Accept if no blacklist match
}

// Wikimedia Commons - Get multiple images with relevance filtering
async function getWikimediaImages(placeName: string, city: string, count: number = 4): Promise<string[]> {
    const images: string[] = [];

    // Try multiple search variations for better matches
    const searchVariations = [
        `${placeName} ${city}`,
        placeName, // Just the place name
    ];

    for (const searchTerm of searchVariations) {
        if (images.length >= count) break;

        try {
            const params = new URLSearchParams({
                action: 'query',
                format: 'json',
                generator: 'search',
                gsrsearch: searchTerm,
                gsrlimit: String((count - images.length) + 4), // Request extra to filter
                prop: 'imageinfo',
                iiprop: 'url|size|mime',
                iiurlwidth: '800',
                origin: '*',
            });

            const response = await fetch(`${WIKIMEDIA_SEARCH}?${params}`, {
                headers: { 'User-Agent': 'CityWalker/1.0' },
            });

            if (response.ok) {
                const data = await response.json();
                const pages = data.query?.pages;
                if (pages) {
                    for (const page of Object.values(pages) as Array<{ imageinfo?: Array<{ thumburl?: string; mime?: string }> }>) {
                        const imageinfo = page.imageinfo?.[0];
                        // Only include actual images (not SVG, PDF, etc.)
                        if (imageinfo?.thumburl && imageinfo.mime?.startsWith('image/') &&
                            !imageinfo.mime.includes('svg')) {
                            // Filter out irrelevant images
                            if (isRelevantImage(imageinfo.thumburl, placeName)) {
                                if (!images.includes(imageinfo.thumburl)) {
                                    images.push(imageinfo.thumburl);
                                    if (images.length >= count) break;
                                }
                            }
                        }
                    }
                }
            }
        } catch {
            // Continue with next variation
        }
    }
    return images;
}

// Unsplash - Get multiple atmospheric photos
async function getUnsplashImages(placeName: string, city: string, type: string | undefined, count: number = 3): Promise<string[]> {
    if (!UNSPLASH_ACCESS_KEY) return [];

    // Build search query based on place type
    let searchQuery = `${placeName} ${city}`;
    const genericTypes = ['cafe', 'bar', 'club', 'restaurant', 'market'];
    if (type && genericTypes.includes(type)) {
        searchQuery = `${type} ${city}`;
    }

    try {
        const params = new URLSearchParams({
            query: searchQuery,
            per_page: String(count),
            orientation: 'landscape',
        });

        const response = await fetch(`${UNSPLASH_API}?${params}`, {
            headers: { Authorization: `Client-ID ${UNSPLASH_ACCESS_KEY}` },
        });

        if (response.ok) {
            const data = await response.json();
            return (data.results || [])
                .map((r: { urls?: { regular?: string } }) => r.urls?.regular)
                .filter(Boolean);
        }
    } catch {
        // Return empty array
    }
    return [];
}

const PIXABAY_API = 'https://pixabay.com/api/';
const PIXABAY_API_KEY = process.env.PIXABAY_API_KEY;

// Pixabay - Get multiple photos (free API)
async function getPixabayImages(placeName: string, city: string, count: number = 3): Promise<string[]> {
    if (!PIXABAY_API_KEY) return [];

    // Try specific place first, then city-themed
    const queries = [
        `${placeName} ${city}`.replace(/[()]/g, ''),
        `${city} tourism`,
    ];

    const images: string[] = [];

    for (const query of queries) {
        if (images.length >= count) break;

        try {
            const params = new URLSearchParams({
                key: PIXABAY_API_KEY,
                q: query,
                image_type: 'photo',
                category: 'places',
                per_page: String(count),
                safesearch: 'true',
            });

            const response = await fetch(`${PIXABAY_API}?${params}`);

            if (response.ok) {
                const data = await response.json();
                for (const hit of data.hits || []) {
                    if (hit.webformatURL && images.length < count) {
                        if (!images.includes(hit.webformatURL)) {
                            images.push(hit.webformatURL);
                        }
                    }
                }
            }
        } catch {
            // Continue with next query
        }
    }
    return images;
}

// City-themed atmospheric fallback images
function getCityThemedFallbackImages(city: string, type?: string): string[] {
    // Use city-themed Unsplash source URLs that dynamically pull relevant images
    const cityQuery = encodeURIComponent(`${city} travel`);
    const typeQuery = type ? encodeURIComponent(`${type} ${city}`) : cityQuery;

    return [
        `https://source.unsplash.com/800x600/?${typeQuery}`,
        `https://source.unsplash.com/800x600/?${cityQuery}`,
    ];
}

// Main function: Get multiple images for a place
async function getMultipleImages(
    placeName: string,
    city: string,
    type?: string
): Promise<{ images: string[]; sources: string[] }> {
    const images: string[] = [];
    const sources: string[] = [];

    // Fetch from all sources in parallel for speed
    const [wikiImage, wikimediaImages, unsplashImages, pixabayImages] = await Promise.all([
        getWikipediaImage(placeName, city),
        getWikimediaImages(placeName, city, 3),
        getUnsplashImages(placeName, city, type, 2),
        getPixabayImages(placeName, city, 2),
    ]);

    // Add Wikipedia main image first (best quality for landmarks)
    if (wikiImage) {
        images.push(wikiImage);
        sources.push('wikipedia');
    }

    // Add Wikimedia images (dedupe with Wikipedia)
    for (const img of wikimediaImages) {
        if (!images.includes(img) && images.length < 5) {
            images.push(img);
            sources.push('wikimedia');
        }
    }

    // Add Unsplash images
    for (const img of unsplashImages) {
        if (!images.includes(img) && images.length < 5) {
            images.push(img);
            sources.push('unsplash');
        }
    }

    // Add Pixabay images if we still need more
    for (const img of pixabayImages) {
        if (!images.includes(img) && images.length < 5) {
            images.push(img);
            sources.push('pixabay');
        }
    }

    // Fallback to city-themed atmospheric images if we have less than 2 images
    if (images.length < 2) {
        const fallbackImages = getCityThemedFallbackImages(city, type);
        for (const img of fallbackImages) {
            if (!images.includes(img) && images.length < 3) {
                images.push(img);
                sources.push('city-themed');
            }
        }
    }

    return { images, sources };
}

export async function POST(req: Request) {
    try {
        const body = await req.json();
        const parsed = imageRequestSchema.safeParse(body);

        if (!parsed.success) {
            return Response.json(
                { error: 'Invalid input', details: parsed.error.issues },
                { status: 400 }
            );
        }

        const { places } = parsed.data;

        // Fetch images for all places in parallel (with batch limit)
        const batchSize = 3; // Lower batch size since each place now fetches multiple
        const results: PlaceImages[] = [];

        for (let i = 0; i < places.length; i += batchSize) {
            const batch = places.slice(i, i + batchSize);
            const batchPromises = batch.map(async (place) => {
                const { images, sources } = await getMultipleImages(place.name, place.city, place.type);
                return { name: place.name, images, sources };
            });

            const batchResults = await Promise.all(batchPromises);
            results.push(...batchResults);
        }

        // Log stats
        const totalImages = results.reduce((sum, r) => sum + r.images.length, 0);
        console.log(`Multi-image fetch: ${results.length} places, ${totalImages} total images`);

        return Response.json({ success: true, results });
    } catch (error) {
        console.error('Image API error:', error);
        return Response.json({ error: 'Failed to fetch images' }, { status: 500 });
    }
}
