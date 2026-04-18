# Wiki Development Guide

## Project Overview

This wiki provides comprehensive documentation for **orooborOS** - a modern immutable Arch Linux distribution built with systemd-boot, Btrfs snapshots, and a Python FSM installer. The documentation is built using **Astro + Starlight** and provides multi-language support (English, Spanish, German).

## Tech Stack

### Core Technologies

- **Astro**: Static site generator with React-like components
- **Starlight**: Documentation theme built on Astro with:
  - Built-in search
  - Multi-language support
  - Responsive design
  - Dark/light mode
  - Table of contents
  - Admonitions and components
- **TypeScript**: For component development
- **Tailwind CSS**: For styling with custom emerald theme

### Supporting Tools

- **Node.js**: Runtime environment (v18+)
- **pnpm**: Package manager (faster npm alternative)
- **ESLint**: Code linting
- **Prettier**: Code formatting
- **Remark**: Markdown processing

## Project Structure

```
ouroborOS-wiki/
├── wiki/                          # Main wiki directory
│   ├── astro.config.mjs           # Astro configuration
│   ├── tsconfig.json              # TypeScript configuration  
│   ├── src/
│   │   ├── components/            # Reusable components
│   │   ├── content/               # Markdown content files
│   │   │   └── docs/              # Documentation content
│   │   │       ├── getting-started/     # Getting started guides
│   │   │       ├── installation/        # Installation documentation
│   │   │       ├── system/              # System management
│   │   │       ├── desktop/             # Desktop environments
│   │   │       ├── apps/                # Applications and tools
│   │   │       ├── network/             # Network configuration
│   │   │       ├── security/           # Security features
│   │   │       └── roadmap/             # Development roadmap
│   │   ├── layouts/               # Layout templates
│   │   ├── pages/                 # Static pages
│   │   └── styles/                # CSS styles
│   │       └── custom.css         # Custom emerald theme
│   ├── public/                    # Static assets
│   ├── .gitignore                 # Git ignore rules
│   └── WIKI_DEVELOPMENT.md        # This file
└── README.md                      # Repository root
```

## How to Run Locally

### Prerequisites

```bash
# Node.js 18+ required
node --version  # Should be >= 18.0.0

# pnpm (recommended for speed)
npm install -g pnpm
```

### Setup Instructions

```bash
# Clone the repository
git clone https://github.com/Arkh-Ur/ouroborOS-dev.git
cd ouroborOS-wiki

# Navigate to wiki directory
cd wiki

# Install dependencies
pnpm install

# Start development server
pnpm run dev
```

The wiki will be available at `http://localhost:4321`

### Building for Production

```bash
# Build static site
pnpm run build

# Preview production build
pnpm run preview
```

## How to Add Content

### Content File Structure

Documentation files follow a consistent structure:

```mdx
---
title: Page Title
description: Brief description of the page
slug: url-slug
---

# Main Title

Content goes here...

:::note

This is a note admonition.

:::

```bash
# Code block with syntax highlighting
command --option value
```
```

### File Naming Conventions

- Use kebab-case for filenames: `getting-started.mdx`
- Group related content in subdirectories
- Include `index.mdx` in directory root files

### Content Guidelines

#### Required Elements

Every content file must include:

1. **Frontmatter**: Title, description, slug
2. **Introduction**: Meaningful content explaining the topic
3. **Code Blocks**: At least one with proper syntax highlighting
4. **Admonitions**: At least one (:::note, :::tip, :::caution, :::danger)
5. **Tabs**: Where applicable, especially for alternative approaches
6. **"Content coming soon..."**: Placeholder for future expansion

#### Writing Style

- Use clear, concise language
- Explain technical concepts briefly
- Provide practical examples
- Include troubleshooting sections
- Link to related documentation
- Use consistent terminology

### Adding New Sections

1. **Plan your content**: Outline the structure and key topics
2. **Create the directory**: Create appropriate subdirectories
3. **Write content files**: Follow the naming and structure conventions
4. **Update sidebar**: Add new entries to `astro.config.mjs`
5. **Test locally**: Ensure pages render correctly
6. **Add translations**: For English, Spanish, and German

## Sidebar Structure Reference

### Current Sidebar Structure

```javascript
sidebar: [
  {
    label: 'Getting Started',
    items: [
      { label: 'What is ouroborOS?', href: '/getting-started/what-is-ouroboros/' },
      { label: 'Why ouroborOS?', href: '/getting-started/why-ouroboros/' },
      { label: 'Architecture', href: '/getting-started/architecture/' },
    ],
  },
  {
    label: 'Installation',
    items: [
      { label: 'Requirements', href: '/installation/requirements/' },
      { label: 'Interactive Mode', href: '/installation/interactive/' },
      { label: 'Unattended Mode', href: '/installation/unattended/' },
      { label: 'Configuration Reference', href: '/installation/config-reference/' },
    ],
  },
  // ... other sections
],
```

### Adding New Items

1. **Choose appropriate section**: Place related content together
2. **Follow hierarchy**: Use nested objects for subsections
3. **Use consistent naming**: Match file names and labels
4. **Update navigation**: Ensure all links work

## Color Palette Reference

### Theme Colors

The wiki uses an emerald/teal color palette based on ouroborOS identity:

```css
/* Dark mode colors */
:root {
  --starlight-color-accent: #10b981;    /* Emerald */
  --starlight-background: #0f172a;      /* Very dark */
  --starlight-surface: #1e293b;         /* Card background */
  --starlight-text: #f1f5f9;           /* Primary text */
  --starlight-text-secondary: #94a3b8;  /* Secondary text */
}

/* Light mode colors */
:root {
  --starlight-color-accent: #059669;    /* Dark emerald */
  --starlight-background: #ffffff;      /* White */
  --starlight-surface: #f8fafc;         /* Light gray */
  --starlight-text: #0f172a;            /* Dark text */
  --starlight-text-secondary: #64748b;  /* Medium gray */
}
```

### Usage Guidelines

- **Primary accent**: Used for links, buttons, and important elements
- **Background colors**: Differentiate between content areas
- **Text hierarchy**: Use proper contrast ratios
- **Consistency**: Maintain color scheme across all pages

## Content Guidelines

### Code Blocks

**Requirements:**
- Use proper syntax highlighting
- Include comments explaining important parts
- Show both commands and expected output
- Use tabs for alternative approaches

**Example:**
```bash
# Install package with our-pac
our-pac install neovim

# Verify installation
neovim --version

# Expected output:
# NVIM v0.9.0
# Build type: Release
```

### Admonitions

Use appropriate admonition types:

- **`:::note`**: Additional information or tips
- **`:::tip`**: Helpful suggestions or best practices
- **`:::caution`**: Important warnings or gotchas
- **`:::danger`**: Critical warnings or potential damage

**Example:**
```mdx
:::caution

Always backup your configuration before making changes. Incorrect configuration may prevent system boot.

:::
```

### Tabs

Use tabs for alternative approaches or different options:

```mdx
<Tabs>
<TabItem label="Method 1">

```bash
# Method 1 using command line
our-pac install neovim
```

</TabItem>
<TabItem label="Method 2">

```bash
# Method 2 using configuration
echo "neovim" >> packages.txt
our-pac install --config-file packages.txt
```

</TabItem>
</Tabs>
```

## Multi-language Support

### Language Structure

```bash
src/content/docs/
├── en/              # English (default)
│   ├── getting-started/
│   ├── installation/
│   └── ...
├── es/              # Spanish
│   ├── getting-started/
│   ├── installation/
│   └── ...
└── de/              # German  
    ├── getting-started/
    ├── installation/
    └── ...
```

### Translation Guidelines

#### Full Translations (First 3 Files)

For "Getting Started" section:
- Translate all content fully
- Maintain technical accuracy
- Keep code examples in English
- Update all links and references

#### Partial Translations (Other Files)

For other sections:
- Translate frontmatter only (title, description)
- Keep body content in English
- Add translation notice at top

**Example notice:**
```mdx
---
title: Network Configuration
description: Network setup and management guide
slug: network/configuration
---

:::note

Esta página aún no está completamente traducida. [Ver en English](/en/network/configuration/)

:::

# Network Configuration

Network content in English...
```

### Adding New Languages

To add support for additional languages:

1. **Create language directory**: `src/content/docs/[lang-code]/`
2. **Copy structure**: Mirror English directory structure
3. **Translate content**: Follow translation guidelines
4. **Update configuration**: Add to `locales` in `astro.config.mjs`
5. **Test navigation**: Ensure all links work correctly

## Deployment Notes

### GitHub Pages Deployment

The wiki is automatically deployed to GitHub Pages when changes are pushed to the main branch.

**Configuration**: `.github/workflows/deploy.yml`

### Preview Deployments

For pull requests, the wiki is automatically deployed to a preview URL.

### Performance Optimization

- **Image optimization**: Use appropriate formats and sizes
- **Code splitting**: Large pages are split into smaller chunks
- **Caching**: Static assets are cached appropriately
- **Search indexing**: Content is optimized for search engines

## Development Workflow

### Local Development

```bash
# Start development server
pnpm run dev

# Run linting
pnpm run lint

# Format code
pnpm run format

# Build project
pnpm run build
```

### Content Updates

1. **Edit content files**: Make changes to `.mdx` files
2. **Test locally**: Use `pnpm run dev` to preview changes
3. **Commit changes**: Follow conventional commit format
4. **Push to repository**: Triggers automatic deployment

### Quality Assurance

- **Content validation**: Check for broken links
- **Code quality**: Ensure consistent formatting
- **Performance**: Monitor build times and page load
- **Accessibility**: Check for proper contrast and navigation

## Troubleshooting

### Common Issues

**Missing CSS or styles**:
```bash
# Clear cache
rm -rf .astro/
pnpm run dev
```

**Build errors**:
```bash
# Check TypeScript errors
pnpm run lint

# Reinstall dependencies
rm -rf node_modules
pnpm install
```

**Missing content**:
- Verify file paths in sidebar configuration
- Check frontmatter for correct slug
- Ensure file extensions are `.mdx`

### Getting Help

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions or share ideas
- **Discord**: Join community chat for real-time help

## Contributing

Contributions are welcome! Please see the [Contributing Guidelines](/roadmap/contributing/) for detailed information on how to contribute to this project.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.