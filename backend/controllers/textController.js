const { spawn } = require("child_process");
const path = require("path");

exports.redactText = (req, res) => {

  if (!req.file) {
    return res.status(400).json({ error: "No file uploaded" });
  }
  console.log("Received file:", req.file.originalname);

  const text = req.file.buffer.toString("utf-8");

  const level = req.body.redaction_level
  
  const scriptPath = path.join(
    __dirname,
    "../services/text/main.py"
  );

  const py = spawn("C:\\Users\\Satyam\\miniconda3\\envs\\privguardtext\\python.exe", [scriptPath, level]);

  let result = "";
  let error = "";

  py.stdin.write(text);
  py.stdin.end();

  py.stdout.on("data", (data) => {
    result += data.toString();
  });

  py.stderr.on("data", (data) => {
    error += data.toString();
  });

  py.on("close", (code) => {
    if (code !== 0) {
      return res.status(500).json({ error });
    }
    res.json({ redacted: result });
  });
};
