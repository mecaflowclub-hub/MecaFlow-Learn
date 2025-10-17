const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

class FileUtils {
  static ensureDirectoryExists(dirPath) {
    if (!fs.existsSync(dirPath)) {
      fs.mkdirSync(dirPath, { recursive: true });
    }
  }

  static generateUniqueFileName(originalName, userId) {
    const ext = path.extname(originalName);
    const timestamp = Date.now();
    const randomHash = crypto.randomBytes(8).toString('hex');
    return `${userId}-${timestamp}-${randomHash}${ext}`;
  }

  static getFileSize(filePath) {
    try {
      const stats = fs.statSync(filePath);
      return stats.size;
    } catch (error) {
      return 0;
    }
  }

  static deleteFile(filePath) {
    try {
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
        return true;
      }
    } catch (error) {
      console.error('Delete file error:', error);
    }
    return false;
  }

  static cleanupOldFiles(directory, maxAge = 7 * 24 * 60 * 60 * 1000) {
    try {
      const files = fs.readdirSync(directory);
      const now = Date.now();
      
      files.forEach(file => {
        const filePath = path.join(directory, file);
        const stats = fs.statSync(filePath);
        
        if (now - stats.mtime.getTime() > maxAge) {
          fs.unlinkSync(filePath);
          console.log(`Deleted old file: ${file}`);
        }
      });
    } catch (error) {
      console.error('Cleanup error:', error);
    }
  }

  static validateFileType(filename, allowedExtensions) {
    const ext = path.extname(filename).toLowerCase();
    return allowedExtensions.includes(ext);
  }
}

module.exports = FileUtils;