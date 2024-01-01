const targetHost = "api.openai.com"
const targetPathname = "v1"

export async  function onRequest(context) {	
  // context -> https://developers.cloudflare.com/pages/functions/api-reference/#eventcontext
 
  const request = await context.request.clone()

  const url = new URL(request.url)
  url.host = targetHost
  url.pathname = url.pathname.replace('/hellogpt', '/' + targetPathname)
  const newUrl = url.toString()
  
  const newRequest = new Request(newUrl, request);
  newRequest.headers.set('Host', targetHost);

  const response = await fetch(newRequest);
  
  return response
}