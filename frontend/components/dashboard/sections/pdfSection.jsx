'use client';

import { useState } from "react";
import PdfUploadCard from "../pdfUploadCard";
import ProcessingAnimation from "../processingAnimation";
import PdfResultsDisplay from "../pdfResultDisplay";

export default function PdfRedactionSection() {
  const [file, setFile] = useState(null);
  const [redactionLevel, setRedactionLevel] = useState([2]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleFileSelect = (selectedFile) => {
    if (selectedFile && selectedFile.type === "application/pdf") {
      setFile(selectedFile);
      setResult(null);
      setError(null);
    } else {
      setError("Please select a valid .pdf file");
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

      const response = await fetch('http://localhost:8000/pdf', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      // Get the PDF blob from response
      const blob = await response.blob();
      
      // Create object URL for PDF preview
      const pdfUrl = window.URL.createObjectURL(blob);
      
      setResult({
        pdfUrl: pdfUrl,
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
    if (result?.pdfUrl) {
      window.URL.revokeObjectURL(result.pdfUrl);
    }
    setFile(null);
    setResult(null);
    setError(null);
    setRedactionLevel([2]);
  };

  return (
    <div className="max-w-4xl mx-auto">
      {!result && !isProcessing && (
        <PdfUploadCard
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
        <PdfResultsDisplay
          result={result}
          file={file}
          onReset={handleReset}
        />
      )}
    </div>
  );
}