"use client";

import { useState } from "react";
import VideoUploadCard from "../videoUploadCard";
import ProcessingAnimation from "../videoProcessingAnimation";
import VideoResultsDisplay from "../videoResultDisplay";

export default function VideoRedactionSection() {
  const [file, setFile] = useState(null);
  const [redactionLevel, setRedactionLevel] = useState([2]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [jobStatus, setJobStatus] = useState("queued");
  const [referenceImage, setReferenceImage] = useState(null);


  const handleFileSelect = (selectedFile) => {
    if (selectedFile && selectedFile.type.startsWith("video/")) {
      setFile(selectedFile);
      setResult(null);
      setError(null);
    } else {
      setError("Please select a valid video file");
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
      formData.append("file", file);
      formData.append("redaction_level", redactionLevel[0]);
      formData.append("reference_image", referenceImage);
      

      const response = await fetch("http://localhost:8000/video", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      console.log(data)
      const jobId = data.job_id;

      if (!response.ok) {
        setIsProcessing(false);
        throw new Error(`Server error: ${data.error || response.statusText}`);
      }

      if (data.status === "queued") {
        let attempts = 0;
        const maxAttempts = 200; // 10 minutes

        const pollInterval = setInterval(async () => {
          try {
            const pollResponse = await fetch(
              `http://127.0.0.1:7000/status/${jobId}`,
            );

            const pollData = await pollResponse.json();
            setJobStatus(pollData.status);
            console.log("Polling:", pollData);

            // ✅ SUCCESS CASE
            if (pollData.status === "done") {
              clearInterval(pollInterval);

              const finalResponse = await fetch(
                `http://127.0.0.1:7000/download/${jobId}`,
              );

              const blob = await finalResponse.blob();
              const videoUrl = window.URL.createObjectURL(blob);

              setResult({
                videoUrl,
                blob,
                metadata: {
                  original_size: (file.size / 1024).toFixed(2) + " KB",
                  redaction_level: redactionLevel[0],
                  processed_at: new Date().toLocaleString(),
                },
              });

              setIsProcessing(false); // ✅ moved here
            }

            // ❌ FAILURE CASE
            if (pollData.status === "failed") {
              clearInterval(pollInterval);
              setIsProcessing(false);
              throw new Error("Processing failed");
            }

            // ⏱ TIMEOUT SAFETY
            attempts++;
            if (attempts > maxAttempts) {
              clearInterval(pollInterval);
              
              throw new Error("Processing timeout");
              
            }
          } catch (err) {
            clearInterval(pollInterval);
            setError(err.message);
            setIsProcessing(false);
          }
        }, 3000);
      }
    } catch (err) {
      setError(err.message || "Failed to process file. Please try again.");
      setIsProcessing(false);
    } finally {
     
    }
  };

  const handleReset = () => {
    // Clean up object URL to prevent memory leaks
    if (result?.videoUrl) {
      window.URL.revokeObjectURL(result.videoUrl);
    }
    setFile(null);
    setResult(null);
    setError(null);
    setRedactionLevel([2]);
  };

  return (
    <div className="max-w-4xl mx-auto">
      {!result && !isProcessing && (
        <VideoUploadCard
          file={file}
          redactionLevel={redactionLevel}
          error={error}
          isProcessing={isProcessing}
          onFileSelect={handleFileSelect}
          onRedactionLevelChange={setRedactionLevel}
          onSubmit={handleSubmit}
          onReset={handleReset}
          referenceImage={referenceImage}
          setReferenceImage={setReferenceImage}
        />
      )}

      {isProcessing && <ProcessingAnimation status={jobStatus} />}

      {result && (
        <VideoResultsDisplay
          result={result}
          file={file}
          onReset={handleReset}
        />
      )}
    </div>
  );
}
