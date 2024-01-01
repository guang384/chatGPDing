const targetHost = "oapi.dingtalk.com"
const targetPathname = "robot/sendBySession"

export async  function onRequestPost(context) {	
  // context -> https://developers.cloudflare.com/pages/functions/api-reference/#eventcontext
 
  const request = await context.request.clone()

  const url = new URL(request.url)
  url.host = targetHost
  url.pathname = targetPathname
  const newUrl = url.toString()
  
  const newRequest = new Request(newUrl, request);
  newRequest.headers.set('Host', targetHost);

  const response = await fetch(newRequest);
  
  return response
}