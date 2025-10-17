const jwt = require("jsonwebtoken");

const token = "ton_token_ici"; 
const decoded = jwt.decode(token, { complete: true });

console.log(decoded);