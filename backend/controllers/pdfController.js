const axios = require("axios");
const FormData = require("form-data");

const http = require("http");
const https = require("https");

const agent = new http.Agent({ keepAlive: true });

exports.redactPdf = async (req, res) => {
  try {
    console.log("API HIT");

    if (!req.file) {
      console.log("No file received");
      return res.status(400).json({ error: "No PDF uploaded" });
    }

    const redactLevel = req.body.redaction_level;
    const lang = req.body.lang || "eng";

    console.log("File size:", req.file.size);
    console.log("Redaction Level:", redactLevel);

    // Build multipart form
    const form = new FormData();
    form.append("file", req.file.buffer, req.file.originalname);
    form.append("redact_level", redactLevel);
    form.append("lang", lang);

    // Call FastAPI
    const fastApiResponse = await axios.post(
      "http://127.0.0.1:4000/api/pdf/redact",
      form,
      {
        headers: {
          ...form.getHeaders(),
        },
        responseType: "stream", // IMPORTANT for PDF binary
        timeout: 1000 * 60 * 5, // ⬅️ 5 minute timeout (important)
        maxBodyLength: Infinity,
        httpAgent: agent,
        maxContentLength: Infinity
      }
    );

    console.log("Received response from FastAPI");

    // Forward headers
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader(
      "Content-Disposition",
      'attachment; filename="redacted.pdf"'
    );

    // Pipe FastAPI PDF stream to client
    fastApiResponse.data.pipe(res);

  } catch (err) {
    console.error("Controller Error:", err.message);
    if (err.response) {
      console.error("FastAPI Error:", err.response.data);
    }
    res.status(500).json({ error: "PDF redaction failed" });
  }
};
