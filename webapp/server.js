var express = require('express');
var app = express();

app.use("/public", express.static(__dirname));

app.listen(3000, function () {
  console.log('Example app listening on port 3000!');
});
