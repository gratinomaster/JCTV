import requests, re, sys
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
urls = [
 ("FOX News (247.foxnews.com)","https://247.foxnews.com/hls/live/2003586/FNCHLSv3/master.m3u8"),
 ("FOX Business (247.foxbusiness.com)","https://247.foxbusiness.com/hls/live/2003756/FBNHLSv3/master.m3u8"),
 ("ABC linear 2400","https://linear-abcnews-akc-na-west-1.media.dssott.com/dvt2=exp=1789390778~url=%2Flas1%2Fva01%2Fdisneyplus%2Fchannel%2F79449312-79dd-473d-873c-515ebf4b5e5f-1781164031838%2F~psid=c6227f47-a451-4fc7-b65b-3bfbb368a487~did=6cb4f04d-0839-4092-8bd7-0d02beef0afb~country=US~kid=k02~hmac=45016beca8fd4f5674044f04fa510f4cc5a0bd47ede73f7abe9cdebce6ae2682/las1/va01/disneyplus/channel/79449312-79dd-473d-873c-515ebf4b5e5f-1781164031838/cmaf-cenc-ctr-1700K/1700_complete.m3u8"),
]
for name,url in urls:
    try:
        r=requests.get(url,headers={'User-Agent':UA},timeout=20)
        print(name, r.status_code, r.headers.get('content-type'), len(r.content))
    except Exception as e:
        print(name,'ERRO',e)
