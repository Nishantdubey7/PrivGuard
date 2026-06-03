const express = require('express');
const cors = require('cors');
const dotenv = require('dotenv');
const router = require('./router');

dotenv.config();


const app = express();
app.use(cors());

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use('/', router);


app.listen(process.env.port, () => {
  console.log(`Server is running on port ${process.env.port}`);
});

module.exports = app;