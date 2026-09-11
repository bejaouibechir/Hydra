/** Configuration autonome pour tester la logique avant l'installation du template Astro. */
export default {
  esbuild: {
    tsconfigRaw: {
      compilerOptions: {
        target: 'ES2022',
        module: 'ESNext',
        moduleResolution: 'bundler',
        resolveJsonModule: true,
        allowSyntheticDefaultImports: true,
        strict: true,
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/lib/chatbot/**/*.test.ts'],
  },
};
