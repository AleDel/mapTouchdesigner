# replicator1_callbacks
# Callback del Replicator COMP de tiles.
# table_tilelist tiene filas para tiles REALES (con imagen en disco).
# Columnas relevantes: id (row_major_id), name ({zoom}_{tilex}_{tiley}),
#                      tilex, tiley, filePath
# El replicador crea ops con nombre tile_{zoom}_{tilex}_{tiley}.
# Aqui asignamos archivos, cableamos el switch compacto y llenamos el tex3d.


def onRemoveReplicant(comp, replicant):
	return


def onReplicate(comp, allOps, newOps, template, master):
	dat   = op('table_tilelist')
	sw    = op('switch_tiles')
	tex3d = op('tiles_tex3d1')

	# Lookup (tilex, tiley) -> filePath  y  (tilex, tiley) -> row_major_id
	coord_to_file = {}
	coord_to_id   = {}
	for r in range(1, dat.numRows):
		try:
			rid = int(dat[r, 'id'])
			tx  = int(dat[r, 'tilex'])
			ty  = int(dat[r, 'tiley'])
			fp  = str(dat[r, 'filePath'])
			coord_to_file[(tx, ty)] = fp
			coord_to_id[(tx, ty)]   = rid
		except:
			pass

	# Helper: parsea nombre tile_{zoom}_{tilex}_{tiley} -> (tilex, tiley) o None
	def tile_coords(tile_op):
		parts = tile_op.name.split('_')
		if len(parts) == 4:
			try:
				return (int(parts[2]), int(parts[3]))
			except:
				pass
		return None

	# Asignar archivo a cada op replicado
	for tile_op in allOps:
		coords = tile_coords(tile_op)
		tile_op.par.file = coord_to_file.get(coords, '') if coords else ''

	# Cablear switch: solo ops con nombre valido tile_{z}_{x}_{y},
	# ordenados por row_major_id ascendente (igual que uIds en el GLSL).
	if sw is None:
		return
	real_ops   = [o for o in allOps if tile_coords(o) is not None]
	sorted_ops = sorted(real_ops, key=lambda o: coord_to_id.get(tile_coords(o), 999999))
	sw.setInputs(sorted_ops)

	if tex3d is None or not sorted_ops:
		return

	n = len(sorted_ops)

	tex3d.par.cachesize = n
	sw.par.index.expr = 'int(me.time.frame - 1)'
	tex3d.par.prefillpulse.pulse()
	
	return
