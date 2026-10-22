// Sends every request for www.model-prices.com to the same path on model-prices.com.
export default {
  fetch(request) {
    const url = new URL(request.url);
    url.hostname = "model-prices.com";
    return Response.redirect(url.toString(), 301);
  },
};
