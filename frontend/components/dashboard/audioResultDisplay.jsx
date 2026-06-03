'use client';

import { CheckCircle2, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AudioResultsDisplay({ result, file, onReset }) {
  const handleDownload = () => {
    if (!result?.blob) return;

    const url = window.URL.createObjectURL(result.blob);
    const a = document.createElement("a");
    a.href = url;
    
    const originalExtension = file?.name?.split('.').pop() || 'mp3';
    a.download = file?.name?.replace(`.${originalExtension}`, `_redacted.${originalExtension}`) || "redacted_audio.mp3";

    document.body.appendChild(a);
    a.click();

    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
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
                Audio Redaction Complete
              </h3>
              <p className="text-gray-400">
                Your audio has been successfully redacted
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Audio Player */}
      <Card className="bg-white/[0.02] border-white/5 backdrop-blur-sm">
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-4">
            <CardTitle className="text-xl text-white">
              Redacted Audio Player
            </CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              className="bg-white/5 border-white/10 hover:bg-white/10 text-white"
            >
              <Download className="w-4 h-4 mr-2" />
              Download
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="bg-gradient-to-br from-green-500/10 to-emerald-500/10 rounded-xl p-8 border border-green-500/20">
            <div className="text-center mb-4">
              <p className="text-white font-semibold mb-1">{file?.name}</p>
              <p className="text-sm text-gray-500">Redacted Audio</p>
            </div>
            
            {/* Native HTML5 Audio Player */}
            <audio 
              controls 
              src={result.audioUrl} 
              className="w-full"
              style={{
                filter: 'invert(1) hue-rotate(180deg)',
                borderRadius: '8px'
              }}
            />
          </div>
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
          Process Another Audio File
        </Button>
      </div>
    </div>
  );
}