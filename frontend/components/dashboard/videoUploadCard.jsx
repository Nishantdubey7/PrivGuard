"use client";

import { FileText, Upload, Zap, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { videoRedactionLevels } from "@/lib/constants/sections";

export default function VideoUploadCard({
  file,
  redactionLevel,
  error,
  isProcessing,
  onFileSelect,
  onRedactionLevelChange,
  onSubmit,
  onReset,
  referenceImage,
  setReferenceImage
}) {
  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      onFileSelect(selectedFile);
    }
  };

  return (
    <Card className="bg-white/[0.02] border-white/5 backdrop-blur-sm mb-8">
      <CardHeader>
        <CardTitle className="text-2xl text-white flex items-center gap-3">
          <div className="p-2 rounded-xl bg-gradient-to-br from-violet-500 to-purple-500">
            <FileText className="w-5 h-5 text-white" />
          </div>
          Video File Redaction
        </CardTitle>
        <CardDescription className="text-gray-400">
          Upload a video file and select the redaction method
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-8">
        {/* File Upload */}
        <div>
          <label className="block text-sm font-semibold text-gray-300 mb-3">
            Select File
          </label>
          <div className="relative">
            <input
              type="file"
              accept=".mp4,.avi,.mov,.mkv,application/mp4"
              onChange={handleFileChange}
              className="hidden"
              id="video-file-upload"
              disabled={isProcessing}
            />
            <label
              htmlFor="video-file-upload"
              className={`block border-2 border-dashed rounded-2xl p-12 text-center transition-all duration-300 ${
                file
                  ? "border-violet-500/50 bg-violet-500/5"
                  : "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.05]"
              } ${isProcessing ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
            >
              <div className="flex flex-col items-center gap-4">
                {file ? (
                  <>
                    <div className="p-4 rounded-2xl bg-gradient-to-br from-violet-500 to-purple-500">
                      <FileText className="w-8 h-8 text-white" />
                    </div>
                    <div>
                      <p className="text-lg font-semibold text-white mb-1">
                        {file.name}
                      </p>
                      <p className="text-sm text-gray-500">
                        {(file.size / 1024).toFixed(2)} KB
                      </p>
                    </div>
                    {!isProcessing && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.preventDefault();
                          onReset();
                        }}
                        className="text-gray-400 hover:text-white hover:bg-white/10"
                      >
                        Change File
                      </Button>
                    )}
                  </>
                ) : (
                  <>
                    <Upload className="w-12 h-12 text-gray-500" />
                    <div>
                      <p className="text-lg font-semibold text-white mb-1">
                        Click to upload or drag and drop
                      </p>
                      <p className="text-sm text-gray-500">Video files only</p>
                    </div>
                  </>
                )}
              </div>
            </label>
          </div>
        </div>

        {/* Redaction Level Slider */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <label className="text-sm font-semibold text-gray-300">
              Redaction Method
            </label>
            <Badge
              className={`${videoRedactionLevels[redactionLevel[0]].color} bg-white/5 border-0`}
            >
              {videoRedactionLevels[redactionLevel[0]].label}
            </Badge>
          </div>

          <div className="relative px-2">
            <Slider
              value={redactionLevel}
              onValueChange={onRedactionLevelChange}
              min={1}
              max={4}
              step={1}
              disabled={isProcessing}
              className="mb-4"
            />

            <div className="flex justify-between text-xs text-gray-500 px-1">
              <span className="text-center flex-1">Face</span>
              <span className="text-center flex-1">Plate + PII</span>
              <span className="text-center flex-1">Multi-Object</span>
              <span className="text-center flex-1">Identity-Preserving</span>
            </div>
          </div>

          <div className="text-sm text-gray-400 mt-3 bg-white/[0.02] p-4 rounded-lg border border-white/5 space-y-2">
            <p className="font-semibold text-gray-300">
              {videoRedactionLevels[redactionLevel[0]].label}
            </p>
            <p>{videoRedactionLevels[redactionLevel[0]].description}</p>
          </div>
        </div>

        {/* Reference Image Upload (ONLY for mode 4) */}
        {redactionLevel[0] === 4 && (
          <div>
            <label className="block text-sm font-semibold text-gray-300 mb-3">
              Reference Face Image
            </label>

            <div className="relative">
              <input
                type="file"
                accept="image/*"
                onChange={(e) => {
                  const img = e.target.files[0];
                  if (img) setReferenceImage(img);
                }}
                className="hidden"
                id="reference-image-upload"
                disabled={isProcessing}
              />

              <label
                htmlFor="reference-image-upload"
                className={`block border-2 border-dashed rounded-xl p-6 text-center transition-all duration-300 ${
                  referenceImage
                    ? "border-violet-500/50 bg-violet-500/5"
                    : "border-white/10 bg-white/[0.02] hover:border-white/20"
                } ${isProcessing ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
              >
                {referenceImage ? (
                  <div className="text-sm text-gray-300">
                    {referenceImage.name}
                  </div>
                ) : (
                  <div className="text-sm text-gray-500">
                    Upload reference face (used to preserve identity)
                  </div>
                )}
              </label>
            </div>
          </div>
        )}

        {/* Error Alert */}
        {error && (
          <Alert className="bg-red-500/10 border-red-500/20 text-red-400">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Submit Button */}
        <Button
          onClick={onSubmit}
          disabled={!file || isProcessing}
          className="w-full bg-gradient-to-r from-violet-500 to-purple-600 hover:from-violet-400 hover:to-purple-500 text-white border-0 shadow-lg shadow-purple-500/20 hover:shadow-purple-500/40 transition-all duration-300 h-14 text-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Zap className="w-5 h-5 mr-2" />
          Redact Video
        </Button>
      </CardContent>
    </Card>
  );
}
