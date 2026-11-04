/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  // `next dev` only: its floating indicator sits over the sidebar's bottom corner.
  devIndicators: false,
};

export default nextConfig;
