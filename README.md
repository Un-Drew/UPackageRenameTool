# Unreal Package Rename Tool
A poorly written, poorly organised tool that allows one to rename entries in an Unreal package's name table. Useful when you want to rename a script package without losing your custom objects/class references from map and content packages.

<img src="https://user-images.githubusercontent.com/69184314/177106099-421bf518-ae32-4c15-b70a-778229e2484f.png" alt="drawing" height="600"/>

.upk, .umap, .udk, .utx, .uax, .unr are examples of Unreal packages. While .u files use the same format, it's recommended that you properly edit and recompile your script files instead of using this as a shortcut (was not tested with them and I won't make an effort to support them).

# When should I use this?
- As mentioned above, this tool may be used to change the name of a package referenced in other packages, if that package file needs to be renamed. For example, if you renamed a package file with the name `FuckingPlaceholder.upk` into `StillCantThinkOfAName.upk`, you may use this tool to rename `FuckingPlaceholder` into `StillCantThinkOfAName` on any package that might reference it (.upk or .umap).

  Note: When renaming a non-script package file, it's recommended to use this tool on that file as well, as some packages may reference themselves (for some reason??).

  Note 2: When renaming a script package file, make sure you also rename any usage of it from .ini files.

  Note 3: Hypothetically, another object may share the same name as the package you're trying to rename. If that happens, that object will be renamed as well. I may update the script in the future, to prevent something like this from happening, but no promises.

  Note 4: This does NOT support Cooked UE3 packages.

- This may also be used to rename script names, for example: after renaming `MyClass.uc` to `NotMyClass.uc`, you'll need to use this tool on map/content files to rename `MyClass` into `NotMyClass`. For UE3, you'll also need to rename its Default Archetype: `Default__MyClass` into `Default__NotMyClass`.

  Note: In UE3, due to how it saves object names, this will also affect names with the format `MyClass_X`.

# What do these Properties™ mean?
- The General Properties are made up of Source Directory, File Name/Type and Output Folder. They're all required, and they dictate what files it should open, and where they should be exported. You can hover on each name for more info.

- The Rename Table is where you can decide which names should be replaced. The layout should be pretty self explanatory. You may also save/load the rename table as an .xml file.

  Note: Old Name and New Name are CASE SENSITIVE.

# How does this work?
Due to how often Unreal packages use absolute byte positions, it wouldn't have been realistic to try to modify and change the length of the name table, which is at the top of the file, and offset EACH position for EACH native asset type. Instead, it saves a new name table at the bottom of the file, ensuring that byte positions are left intact. While this does mean that the file will increase in size, this can be fixed by resaving the package in the Editor.

# Where do I download this?
You can download the .exe file from <a href="https://github.com/Un-Drew/UPackageRenameTool/releases">Releases</a>, OR download the source code if you wish to run it on another OS (I can't guarantee that it'll work on anything other than Windows, but I'm still giving the option). I don't know the minimum python version required to run this .py file, but it did run with Python 3.9.

You may make and distribute alternative versions of this, but please provide credit with the original GitHub page ( https://github.com/Un-Drew/UPackageRenameTool ).
