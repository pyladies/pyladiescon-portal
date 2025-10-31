# Volunteer Template Tags

This document describes the template tags available for rendering volunteer-related content.

## volunteer_tags

The `volunteer_tags` module provides template tags for rendering volunteer profile information.

### Usage

Load the template tags in your template:

```html
{% load volunteer_tags %}
```

### Available Tags

#### `volunteer_languages_badges`

An inclusion tag that renders volunteer languages as Bootstrap badges.

**Usage:**
```html
{% volunteer_languages_badges volunteer_profile %}
```

**With custom CSS classes:**
```html
{% volunteer_languages_badges volunteer_profile "custom-badge-class" %}
```

**Parameters:**
- `volunteer_profile`: A VolunteerProfile instance with a language relationship
- `css_classes` (optional): Custom CSS classes for the badges (default: "badge bg-info text-dark me-1")

**Example:**
```html
<!-- In your template -->
{% load volunteer_tags %}

<div class="languages-section">
    <h4>Languages:</h4>
    {% volunteer_languages_badges object %}
</div>
```

#### `render_volunteer_languages`

A simple tag that returns volunteer languages as HTML badges.

**Usage:**
```html
{% render_volunteer_languages volunteer_profile %}
```

**With custom CSS classes:**
```html
{% render_volunteer_languages volunteer_profile "my-custom-class" %}
```

**Parameters:**
- `volunteer_profile`: A VolunteerProfile instance with a language relationship  
- `css_classes` (optional): Custom CSS classes for the badges (default: "badge bg-info text-dark me-1")

**Example:**
```html
<!-- In your template -->
{% load volunteer_tags %}

<div class="volunteer-info">
    Languages: {% render_volunteer_languages volunteer_profile %}
</div>
```

## Migration from Manual Rendering

### Before (duplicated code):
```html
{% for language in object.language.all %}
    <span class="badge bg-info text-dark me-1">{{ language.name }}</span>
{% endfor %}
```

### After (using template tag):
```html
{% load volunteer_tags %}
{% volunteer_languages_badges object %}
```

## Benefits

1. **DRY Principle**: Eliminates code duplication across templates
2. **Consistency**: Ensures consistent styling and structure
3. **Maintainability**: Changes to language rendering only need to be made in one place
4. **Flexibility**: Supports custom CSS classes for different use cases
5. **Reusability**: Can be used in any template that needs to display volunteer languages