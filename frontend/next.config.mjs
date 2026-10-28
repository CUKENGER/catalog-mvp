/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  async rewrites() {
    return [
      {
        source: "/storage/:path*",
        destination: "http://minio:9000/:path*",
      },
    ];
  },
};

export default nextConfig;
