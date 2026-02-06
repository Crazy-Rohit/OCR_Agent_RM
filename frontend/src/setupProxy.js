const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function (app) {
  app.use(
    ["/ocr"],
    createProxyMiddleware({
      target: process.env.REACT_APP_BACKEND_URL || "http://localhost:8000",
      changeOrigin: true,
    })
  );
};
