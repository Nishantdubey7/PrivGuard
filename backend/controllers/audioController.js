// controllers/audioRedaction.controller.js
const axios = require("axios");
const FormData = require("form-data");
const fs = require("fs");

exports.redactAudio = async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ message: "Audio file is required" });
    }

    // Create form-data
    const form = new FormData();
    // 👇 use buffer instead of path
    form.append("file", req.file.buffer, req.file.originalname);
    form.append("redaction_level", req.body.redaction_level);

    // Call FastAPI
    const fastApiResponse = await axios.post(
      "http://localhost:5000/api/audio",
      //  "http://35.200.145.250/api/audio/lvl1",
      form,
      {
        headers: {
          ...form.getHeaders(),
        },
        responseType: "stream", // important for binary audio
      },
    );

    // Set headers for audio download/stream
    res.setHeader("Content-Type", "audio/wav");
    res.setHeader("Content-Disposition", 'attachment; filename="redacted.wav"');

    // Pipe FastAPI audio stream to client
    fastApiResponse.data.pipe(res);
  } catch (error) {
    console.error(
      "Audio redaction error:",
      error?.response?.data || error.message,
    );

    return res.status(500).json({
      message: "Audio redaction failed",
      error: error?.response?.statusText || error.message,
    });
  }
};
