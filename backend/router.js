const router = require('express').Router();
const textController = require('./controllers/textController');
const pdfController = require('./controllers/pdfController');
const audioController = require('./controllers/audioController');
const videoController = require('./controllers/videoController');
const imageController = require('./controllers/imageController');
const multer = require("multer");

const upload = multer(); 



router.get('/', (req, res) => {
  res.send('Backend is bhaaging 🏃‍♂️🏃‍♂️🏃‍♂️');
});

router.post('/text', upload.single("file"), textController.redactText);

router.post('/pdf', upload.single("file"), pdfController.redactPdf);

router.post('/audio', upload.single("file"), audioController.redactAudio);

router.post('/video', upload.fields([
    { name: "file", maxCount: 1 },
    { name: "reference_image", maxCount: 1 },
  ]), videoController.redactVideo);

router.post('/image', upload.fields([
    { name: "file", maxCount: 1 },
    { name: "reference_image", maxCount: 1 },
  ]), imageController.redactImage);

module.exports = router;