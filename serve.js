const express = require('express');
const app = express();

app.use(express.static('static-files'));

app.listen(5000, () => {
  console.log('Static server running on http://localhost:5000');
});
