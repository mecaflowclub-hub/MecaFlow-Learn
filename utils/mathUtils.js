class MathUtils {
  static calculatePercentageError(actual, expected) {
    if (expected === 0) return actual === 0 ? 0 : 100;
    return Math.abs((actual - expected) / expected) * 100;
  }

  static roundToDecimalPlaces(number, decimalPlaces = 3) {
    const factor = Math.pow(10, decimalPlaces);
    return Math.round(number * factor) / factor;
  }

  static normalizeVector(vector) {
    const magnitude = Math.sqrt(
      vector.x * vector.x + 
      vector.y * vector.y + 
      vector.z * vector.z
    );
    
    if (magnitude === 0) return { x: 0, y: 0, z: 0 };
    
    return {
      x: vector.x / magnitude,
      y: vector.y / magnitude,
      z: vector.z / magnitude
    };
  }

  static calculateDistance3D(point1, point2) {
    const dx = point2.x - point1.x;
    const dy = point2.y - point1.y;
    const dz = point2.z - point1.z;
    
    return Math.sqrt(dx * dx + dy * dy + dz * dz);
  }

  static convertUnits(value, fromUnit, toUnit) {
    const conversions = {
      // Length conversions to mm
      'm_to_mm': 1000,
      'cm_to_mm': 10,
      'in_to_mm': 25.4,
      
      // Volume conversions to mm³
      'm3_to_mm3': 1e9,
      'cm3_to_mm3': 1000,
      'in3_to_mm3': 16387.064,
      
      // Moment conversions to mm⁴
      'm4_to_mm4': 1e12,
      'cm4_to_mm4': 1e8,
      'in4_to_mm4': 416231.4
    };
    
    const conversionKey = `${fromUnit}_to_${toUnit}`;
    const factor = conversions[conversionKey];
    
    return factor ? value * factor : value;
  }

  static isWithinTolerance(value1, value2, tolerance) {
    const error = Math.abs((value1 - value2) / value2);
    return error <= tolerance;
  }

  static calculateMomentRatios(moments) {
    const { Ixx, Iyy, Izz } = moments;
    
    return {
      IxxToIyy: Iyy !== 0 ? Ixx / Iyy : 0,
      IxxToIzz: Izz !== 0 ? Ixx / Izz : 0,
      IyyToIzz: Izz !== 0 ? Iyy / Izz : 0
    };
  }

  static validateGeometryValues(data) {
    const errors = [];
    
    // Volume validation
    if (!data.volume || data.volume <= 0) {
      errors.push('Volume must be positive');
    }
    
    // Moments validation
    if (!data.moments) {
      errors.push('Moments data is required');
    } else {
      const requiredMoments = ['Ixx', 'Iyy', 'Izz'];
      for (const moment of requiredMoments) {
        if (!data.moments[moment] || data.moments[moment] <= 0) {
          errors.push(`${moment} must be positive`);
        }
      }
    }
    
    // Center of mass validation
    if (!data.centerOfMass) {
      errors.push('Center of mass data is required');
    } else {
      const coords = ['x', 'y', 'z'];
      for (const coord of coords) {
        if (data.centerOfMass[coord] === null || 
            data.centerOfMass[coord] === undefined) {
          errors.push(`Center of mass ${coord} coordinate is required`);
        }
      }
    }
    
    return errors;
  }
}

module.exports = MathUtils;