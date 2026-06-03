const axios = require("axios");
const FormData = require("form-data");

const http = require("http");
const https = require("https");

const agent = new http.Agent({ keepAlive: true });

exports.redactImage = async (req, res) => {
  try {
    console.log("API HIT");

    if (!req.files["file"]) {
      console.log("No file received");
      return res.status(400).json({ error: "No Image uploaded" });
    }

    const redactLevel = req.body.redaction_level;
    const referenceImage = req.files["reference_image"]?.[0]; // optional

    if (redactLevel === "4" && !referenceImage) {
      console.log("Mode 4 selected but no reference image provided");
      return res
        .status(400)
        .json({ error: "Reference image required for mode 4" });
    }

    console.log("File size:", req.files["file"][0].size);
    console.log("Redaction Level:", redactLevel);

    // Build multipart form
    const form = new FormData();
    form.append(
      "image",
      req.files["file"][0].buffer,
      req.files["file"][0].originalname,
    );
    form.append("mode", redactLevel);
    // ✅ FIXED
    if (referenceImage) {
      form.append(
        "identity",
        referenceImage.buffer,
        referenceImage.originalname,
      );
    }

    // Call FastAPI
    const fastApiResponse = await axios.post(
      "http://127.0.0.1:7000/image",
      form,
      {
        headers: {
          ...form.getHeaders(),
        },
        responseType: "stream", // IMPORTANT for video binary
        timeout: 1000 * 60 * 5, // ⬅️ 5 minute timeout (important)
        maxBodyLength: Infinity,
        httpAgent: agent,
        maxContentLength: Infinity,
      },
    );

    console.log("Received response from FastAPI");

    // Forward headers
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", 'attachment; filename="redacted.pdf"');

    // Pipe FastAPI PDF stream to client
    fastApiResponse.data.pipe(res);
  } catch (err) {
    console.error("Controller Error:", err.message);
    if (err.response) {
      console.error("FastAPI Error:", err.response.data);
    }
    res.status(500).json({ error: "Image redaction failed" });
  }
};
