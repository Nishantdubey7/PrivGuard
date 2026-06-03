'use client';

import { useState } from "react";
import FileUploadCard from "../fileUploadCard";
import ProcessingAnimation from "../processingAnimation";
import ResultsDisplay from "../resultDisplay";

export default function TextRedactionSection() {
  const [file, setFile] = useState(null);
  const [redactionLevel, setRedactionLevel] = useState([2]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleFileSelect = (selectedFile) => {
    if (selectedFile && selectedFile.type === "text/plain") {
      setFile(selectedFile);
      setResult(null);
      setError(null);
    } else {
      setError("Please select a valid .txt file");
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

      const response = await fetch('http://localhost:8000/text', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message || "Failed to process file. Please try again.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setResult(null);
    setError(null);
    setRedactionLevel([2]);
  };

  return (
    <div className="max-w-4xl mx-auto">
      {!result && !isProcessing && (
        <FileUploadCard
          file={file}
          redactionLevel={redactionLevel}
          error={error}
          isProcessing={isProcessing}
          onFileSelect={handleFileSelect}
          onRedactionLevelChange={setRedactionLevel}
          onSubmit={handleSubmit}
          onReset={handleReset}
          acceptedFileTypes=".txt"
          fileTypeLabel=".txt files only"
        />
      )}

      {isProcessing && <ProcessingAnimation />}

      {result && (
        <ResultsDisplay
          result={result}
          file={file}
          onReset={handleReset}
        />
      )}
    </div>
  );
}