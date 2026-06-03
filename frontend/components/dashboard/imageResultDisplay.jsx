'use client';

import { CheckCircle2, Download, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useState } from "react";

export default function ImageResultsDisplay({ result, file, onReset }) {
  const [zoom, setZoom] = useState(100);

  const handleDownload = () => {
    if (!result?.blob) return;

    const url = window.URL.createObjectURL(result.blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = file?.name?.replace(/\.(jpg|jpeg|png|webp|gif|bmp)$/i, "_privguarded.$1") || "privguarded_image.png";

    document.body.appendChild(a);
    a.click();

    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  const handleZoomIn = () => {
    setZoom(prev => Math.min(prev + 25, 200));
  };

  const handleZoomOut = () => {
    setZoom(prev => Math.max(prev - 25, 50));
  };

  return (
    <div className="space-y-6">
      {/* Success Header */}
      <Card className="bg-gradient-to-r from-green-500/10 to-emerald-500/10 border-green-500/20">
        <CardContent className="py-8">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-full bg-green-500/20">
              <CheckCircle2 className="w-8 h-8 text-green-400" />
            </div>
            <div>
              <h3 className="text-2xl font-bold text-white mb-1">
                Image Redaction Complete
              </h3>
              <p className="text-gray-400">
                Your image has been successfully redacted
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Image Preview */}
      <Card className="bg-white/[0.02] border-white/5 backdrop-blur-sm">
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-4">
            <CardTitle className="text-xl text-white">
              Redacted Image Preview
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleZoomOut}
                disabled={zoom <= 50}
                className="bg-white/5 border-white/10 hover:bg-white/10 text-white"
              >
                <ZoomOut className="w-4 h-4" />
              </Button>
              <span className="text-sm text-gray-400 min-w-[60px] text-center">
                {zoom}%
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={handleZoomIn}
                disabled={zoom >= 200}
                className="bg-white/5 border-white/10 hover:bg-white/10 text-white"
              >
                <ZoomIn className="w-4 h-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                className="bg-white/5 border-white/10 hover:bg-white/10 text-white ml-2"
              >
                <Download className="w-4 h-4 mr-2" />
                Download
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="bg-black/30 rounded-xl border border-white/5 overflow-hidden">
            <div
              className="overflow-auto"
              style={{
                maxHeight: '600px',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'flex-start',
                padding: '20px'
              }}
            >
              {result.imageUrl && (
                <img
                  src={result.imageUrl}
                  alt="Redacted preview"
                  className="rounded-lg shadow-2xl"
                  style={{
                    width: `${zoom}%`,
                    minWidth: '300px',
                    maxWidth: '100%',
                    height: 'auto',
                    transformOrigin: 'top center',
                    display: 'block',
                  }}
                />
              )}
            </div>
          </div>
          <p className="text-sm text-gray-500 mt-4 text-center">
            Use the zoom controls to adjust the preview size
          </p>
        </CardContent>
      </Card>

      {/* Metadata */}
      {result.metadata && (
        <Card className="bg-white/[0.02] border-white/5 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-xl text-white">
              Processing Details
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {Object.entries(result.metadata).map(([key, value]) => (
                <div key={key} className="bg-white/[0.02] p-4 rounded-lg border border-white/5">
                  <p className="text-xs text-gray-500 mb-1 capitalize">
                    {key.replace(/_/g, ' ')}
                  </p>
                  <p className="text-lg font-semibold text-white">
                    {value}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Action Buttons */}
      <div className="flex gap-4">
        <Button
          onClick={onReset}
          className="flex-1 bg-white/5 border border-white/10 hover:bg-white/10 text-white"
        >
          Process Another Image
        </Button>
      </div>
    </div>
  );
}
