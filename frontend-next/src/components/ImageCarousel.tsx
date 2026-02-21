'use client';

/**
 * ImageCarousel — Swipeable image carousel for POI cards
 * Touch/mouse gestures, dot indicators, fade-in loading.
 */

import { useState, useRef, useCallback, useEffect } from 'react';

interface ImageCarouselProps {
  images: string[];
  alt: string;
  className?: string;
  onImageLoad?: () => void;
}

export function ImageCarousel({ images, alt, className = '', onImageLoad }: ImageCarouselProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loadedImages, setLoadedImages] = useState<Set<number>>(() => new Set());
  const [failedImages, setFailedImages] = useState<Set<number>>(() => new Set());
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const startXRef = useRef(0);
  const dragStartedRef = useRef(false);

  useEffect(() => {
    if (currentIndex >= images.length && images.length > 0) {
      setCurrentIndex(images.length - 1);
    }
  }, [images.length, currentIndex]);

  // Preload adjacent images
  useEffect(() => {
    if (images.length <= 1) return;
    const toLoad = [currentIndex];
    if (currentIndex > 0) toLoad.push(currentIndex - 1);
    if (currentIndex < images.length - 1) toLoad.push(currentIndex + 1);
    toLoad.forEach(idx => {
      if (!loadedImages.has(idx) && !failedImages.has(idx)) {
        const img = new window.Image();
        img.src = images[idx];
        img.onload = () => setLoadedImages(prev => { const next = new Set(prev); next.add(idx); return next; });
        img.onerror = () => setFailedImages(prev => { const next = new Set(prev); next.add(idx); return next; });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex, images]);

  const goToSlide = useCallback((index: number) => {
    if (index >= 0 && index < images.length) setCurrentIndex(index);
  }, [images.length]);

  const handleDragStart = useCallback((clientX: number) => {
    startXRef.current = clientX;
    dragStartedRef.current = true;
    setIsDragging(true);
  }, []);

  const handleDragMove = useCallback((clientX: number) => {
    if (!dragStartedRef.current) return;
    setDragOffset(clientX - startXRef.current);
  }, []);

  const handleDragEnd = useCallback(() => {
    if (!dragStartedRef.current) return;
    dragStartedRef.current = false;
    setIsDragging(false);
    const threshold = 50;
    if (dragOffset > threshold && currentIndex > 0) setCurrentIndex(currentIndex - 1);
    else if (dragOffset < -threshold && currentIndex < images.length - 1) setCurrentIndex(currentIndex + 1);
    setDragOffset(0);
  }, [dragOffset, currentIndex, images.length]);

  const handleMouseDown = (e: React.MouseEvent) => { e.preventDefault(); handleDragStart(e.clientX); };
  const handleMouseMove = (e: React.MouseEvent) => handleDragMove(e.clientX);
  const handleMouseUp = () => handleDragEnd();
  const handleMouseLeave = () => { if (dragStartedRef.current) handleDragEnd(); };
  const handleTouchStart = (e: React.TouchEvent) => handleDragStart(e.touches[0].clientX);
  const handleTouchMove = (e: React.TouchEvent) => handleDragMove(e.touches[0].clientX);
  const handleTouchEnd = () => handleDragEnd();

  if (!images.length) {
    return (
      <div className={`flex items-center justify-center ${className}`} style={{ background: 'linear-gradient(145deg, #2a2a4a, #1a1a2e)' }}>
        <div className="flex flex-col items-center gap-1.5 opacity-60">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5">
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15L16 10L5 21" />
          </svg>
          <span className="text-[10px] tracking-wider uppercase" style={{ color: 'rgba(255,255,255,0.35)' }}>No image</span>
        </div>
      </div>
    );
  }

  const showNavigation = images.length > 1;
  const translateX = -currentIndex * 100 + (dragOffset / (containerRef.current?.offsetWidth || 300)) * 100;

  return (
    <div
      ref={containerRef}
      className={`relative overflow-hidden select-none ${className}`}
      onMouseDown={showNavigation ? handleMouseDown : undefined}
      onMouseMove={showNavigation && isDragging ? handleMouseMove : undefined}
      onMouseUp={showNavigation ? handleMouseUp : undefined}
      onMouseLeave={showNavigation ? handleMouseLeave : undefined}
      onTouchStart={showNavigation ? handleTouchStart : undefined}
      onTouchMove={showNavigation ? handleTouchMove : undefined}
      onTouchEnd={showNavigation ? handleTouchEnd : undefined}
      style={{ cursor: showNavigation ? (isDragging ? 'grabbing' : 'grab') : 'default' }}
    >
      {/* Image Track */}
      <div
        className="flex h-full"
        style={{
          transform: `translateX(${translateX}%)`,
          transition: isDragging ? 'none' : 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        {images.map((src, idx) => (
          <div key={idx} className="shrink-0 w-full h-full relative">
            {failedImages.has(idx) ? (
              <div
                className="absolute inset-0 flex items-center justify-center"
                style={{ background: 'linear-gradient(145deg, #2a2a4a, #1a1a2e)' }}
              >
                <div className="flex flex-col items-center gap-1.5 opacity-60">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.45)" strokeWidth="1.5">
                    <rect x="3" y="3" width="18" height="18" rx="3" />
                    <circle cx="8.5" cy="8.5" r="1.5" />
                    <path d="M21 15L16 10L5 21" />
                  </svg>
                  <span className="text-[10px] tracking-wider uppercase" style={{ color: 'rgba(255,255,255,0.3)' }}>Image unavailable</span>
                </div>
              </div>
            ) : (
              <>
                {!loadedImages.has(idx) ? (
                  <div className="absolute inset-0 animate-shimmer" />
                ) : null}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={src}
                  alt={`${alt} - ${idx + 1}`}
                  className={`w-full h-full object-cover transition-opacity duration-300 ${loadedImages.has(idx) ? 'opacity-100' : 'opacity-0'}`}
                  onLoad={() => {
                    setLoadedImages(prev => { const next = new Set(prev); next.add(idx); return next; });
                    if (idx === 0) onImageLoad?.();
                  }}
                  onError={() => setFailedImages(prev => { const next = new Set(prev); next.add(idx); return next; })}
                  draggable={false}
                />
              </>
            )}
          </div>
        ))}
      </div>

      {/* Dot Indicators */}
      {showNavigation ? (
        <div className="absolute bottom-3 left-0 right-0 flex justify-center gap-1.5 z-10">
          {images.map((_, idx) => (
            <button
              key={idx}
              onClick={e => { e.stopPropagation(); goToSlide(idx); }}
              className={`rounded-full transition-all duration-200 ${
                idx === currentIndex ? 'w-6 h-2 bg-white shadow-md' : 'w-2 h-2 bg-white/60 hover:bg-white/80'
              }`}
              aria-label={`Go to image ${idx + 1}`}
            />
          ))}
        </div>
      ) : null}

      {/* Counter badge */}
      {showNavigation ? (
        <div
          className="absolute top-3 right-3 glass-dark text-white text-xs px-2.5 py-1 rounded-full font-medium"
        >
          {currentIndex + 1}/{images.length}
        </div>
      ) : null}

      {/* Bottom gradient for legibility */}
      <div
        className="absolute inset-x-0 bottom-0 h-20 pointer-events-none"
        style={{ background: 'linear-gradient(to top, rgba(26, 26, 46, 0.35), transparent)' }}
      />
    </div>
  );
}
