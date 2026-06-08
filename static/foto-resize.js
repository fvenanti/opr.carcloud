// Redimensiona una imagen seleccionada en un <input type="file"> antes de subirla.
// - Lado mayor maximo: 1600px
// - Re-encodea como JPEG calidad 0.85
// - Reemplaza el FileList del input con el blob comprimido
// Devuelve una promesa que resuelve a una URL de preview (objectURL).

window.resizeFotoInput = async function (input, opts) {
  const maxSide  = (opts && opts.maxSide)  || 1600;
  const quality  = (opts && opts.quality)  || 0.85;
  const file = input.files && input.files[0];
  if (!file || !file.type.startsWith("image/")) return null;

  // Si la imagen ya es chica (< 1.5 MB) no la tocamos
  if (file.size < 1.5 * 1024 * 1024) {
    return URL.createObjectURL(file);
  }

  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) return URL.createObjectURL(file);

  let { width, height } = bitmap;
  const scale = Math.min(1, maxSide / Math.max(width, height));
  const w = Math.round(width  * scale);
  const h = Math.round(height * scale);

  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  canvas.getContext("2d").drawImage(bitmap, 0, 0, w, h);

  const blob = await new Promise(res => canvas.toBlob(res, "image/jpeg", quality));
  if (!blob) return URL.createObjectURL(file);

  const newName = (file.name || "foto").replace(/\.[^.]+$/, "") + ".jpg";
  const newFile = new File([blob], newName, { type: "image/jpeg", lastModified: Date.now() });
  const dt = new DataTransfer();
  dt.items.add(newFile);
  input.files = dt.files;

  return URL.createObjectURL(blob);
};
