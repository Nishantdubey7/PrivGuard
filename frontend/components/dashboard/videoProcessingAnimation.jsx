"use client";

import { Loader2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export default function ProcessingAnimation({ status }) {
  return (
    <Card className="bg-white/[0.02] border-white/5 backdrop-blur-sm">
      <CardContent className="py-16">
        <div className="flex flex-col items-center gap-6">
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-r from-cyan-500 via-violet-500 to-orange-500 rounded-full blur-2xl opacity-30 animate-pulse"></div>
            <div className="relative bg-gradient-to-r from-cyan-500 via-violet-500 to-orange-500 p-6 rounded-full">
              <Loader2 className="w-12 h-12 text-white animate-spin" />
            </div>
          </div>

          <div className="text-center">
            <h3 className="text-2xl font-bold text-white mb-2">
              Analyzing & Redacting
            </h3>
            <p className="text-gray-400">
              Please wait while we process your file...
            </p>
            <p className="text-gray-400">
              {status === "queued" && "Queued... waiting to start"}
              {status === "processing" && "Processing file..."}
              {status === "done" && "Finalizing..."}
            </p>
          </div>

          <div className="flex gap-2 mt-4">
            <div
              className="w-3 h-3 bg-cyan-500 rounded-full animate-bounce"
              style={{ animationDelay: "0ms" }}
            ></div>
            <div
              className="w-3 h-3 bg-violet-500 rounded-full animate-bounce"
              style={{ animationDelay: "150ms" }}
            ></div>
            <div
              className="w-3 h-3 bg-orange-500 rounded-full animate-bounce"
              style={{ animationDelay: "300ms" }}
            ></div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
