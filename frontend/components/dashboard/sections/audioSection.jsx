'use client';

import { useState } from "react";
import AudioUploadCard from "../audioUploadCard";
import ProcessingAnimation from "../processingAnimation";
import AudioResultsDisplay from "../audioResultDisplay";

export default function AudioRedactionSection() {
  const [file, setFile] = useState(null);
  const [redactionLevel, setRedactionLevel] = useState([2]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleFileSelect = (selectedFile) => {
    const validTypes = ["audio/mpeg", "audio/wav", "audio/mp3", "audio/x-wav", "audio/wave", "audio/ogg", "audio/vorbis"];
    const validExtensions = ['.mp3', '.wav', '.ogg'];
    const fileExtension = selectedFile.name.toLowerCase().slice(selectedFile.name.lastIndexOf('.'));
    
    if (selectedFile && (validTypes.includes(selectedFile.type) || validExtensions.includes(fileExtension))) {
      setFile(selectedFile);
      setResult(null);
      setError(null);
    } else {
      setError("Please select a valid audio file (MP3, WAV, OGG)");
      setFile(null);
    }
  };

  const handleSubmit = async () => {
    if (!file) {
      setError("Please select a file first");
      return;
    }

    setIsProcessing(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('redaction_level', redactionLevel[0]);

      const response = await fetch('http://localhost:8000/audio', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      // Get the audio blob from response
      const blob = await response.blob();
      
      // Create object URL for audio playback
      const audioUrl = window.URL.createObjectURL(blob);
      
      setResult({
        audioUrl: audioUrl,
        blob: blob,
        metadata: {
          original_size: (file.size / 1024).toFixed(2) + ' KB',
          redaction_level: redactionLevel[0],
          processed_at: new Date().toLocaleString()
        }
      });
    } catch (err) {
      setError(err.message || "Failed to process file. Please try again.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReset = () => {
    // Clean up object URL to prevent memory leaks
    if (result?.audioUrl) {
      window.URL.revokeObjectURL(result.audioUrl);
    }
    setFile(null);
    setResult(null);
    setError(null);
    setRedactionLevel([2]);
  };

  return (
    <div className="max-w-4xl mx-auto">
      {!result && !isProcessing && (
        <AudioUploadCard
          file={file}
          redactionLevel={redactionLevel}
          error={error}
          isProcessing={isProcessing}
          onFileSelect={handleFileSelect}
          onRedactionLevelChange={setRedactionLevel}
          onSubmit={handleSubmit}
          onReset={handleReset}
        />
      )}

      {isProcessing && <ProcessingAnimation />}

      {result && (
        <AudioResultsDisplay
          result={result}
          file={file}
          onReset={handleReset}
        />
      )}
    </div>
  );
}