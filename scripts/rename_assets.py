import os
import glob
from pathlib import Path

def rename_generated_files(base_dir="generated/posters"):
    """
    Renames the generated files to ensure the poster (.jpg) and social copy (.json)
    share the exact same base name (the blog_id).
    
    Old format:
      [blog_id]_poster.jpg
      [blog_id]_social_copy.json
      
    New format:
      [blog_id].jpg
      [blog_id].json
    """
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"Directory {base_dir} does not exist.")
        return

    renamed_count = 0
    for file_path in base_path.rglob("*"):
        if not file_path.is_file():
            continue
            
        filename = file_path.name
        
        # Keep illustration files as they are (or rename if requested, but they don't have a json pair)
        if filename.endswith("_illustration.jpg"):
            continue
            
        new_name = None
        if filename.endswith("_poster.jpg"):
            new_name = filename.replace("_poster.jpg", ".jpg")
        elif filename.endswith("_social_copy.json"):
            new_name = filename.replace("_social_copy.json", ".json")
            
        if new_name:
            new_path = file_path.with_name(new_name)
            
            # Prevent accidental overwrites if the script is run multiple times
            if not new_path.exists():
                file_path.rename(new_path)
                print(f"Renamed: {filename} -> {new_name}")
                renamed_count += 1
            else:
                print(f"Skipped: {new_name} already exists.")
                # We can safely remove the old dangling file if the new one exists
                # but better to leave it to the user.

    print(f"\nSuccessfully renamed {renamed_count} files.")

if __name__ == "__main__":
    rename_generated_files()
